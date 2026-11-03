"""Pruebas unitarias del cargador y las visualizaciones EDA."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.loader import find_workbook, normalize_columns
from src.data.profile import iqr_outlier_summary, overview_table, safe_category_counts
from src.visualization.eda import (
    _histogram,
    _log_histogram,
    binned_relationship,
    categorical_figures,
    completeness_figures,
    coverage_band,
    distribution_figures,
)
from src.visualization.palette import SURA_FONT_FAMILY, SURA_PALETTE
from src.utils.reporting import _chart_interpretation, build_dashboard_html


class ExplorationTests(unittest.TestCase):
    def test_sura_palette_uses_requested_colors(self) -> None:
        self.assertEqual(
            SURA_PALETTE,
            ("#0033A0", "#00AEC7", "#4EC3E0", "#E3E829", "#FFE946"),
        )
        self.assertIn("Sura Sans", SURA_FONT_FAMILY)

    def test_normalizes_source_headers(self) -> None:
        frame = pd.DataFrame(
            columns=[
                "#",
                "   mesada   ",
                "Capital +Bono",
                "Descapitalizaci\ufffdn",
                "Fecha de Generaci\ufffdn ",
            ]
        )

        result = normalize_columns(frame)

        self.assertEqual(
            result.columns.tolist(),
            [
                "registro",
                "mesada",
                "capital_mas_bono",
                "descapitalizacion",
                "fecha_generacion",
            ],
        )

    def test_duplicate_normalized_headers_raise(self) -> None:
        frame = pd.DataFrame(columns=["Edad", " edad "])

        with self.assertRaisesRegex(ValueError, "duplica"):
            normalize_columns(frame)

    def test_find_workbook_in_raw_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook = root / "data" / "raw" / "Base_Proyecto.xlsx"
            workbook.parent.mkdir(parents=True)
            workbook.touch()

            self.assertEqual(find_workbook(root), workbook)

    def test_histogram_bins_suppress_small_counts(self) -> None:
        frame = pd.DataFrame({"capital": np.arange(1, 1001, dtype=float)})

        histogram = _histogram(frame, "capital")

        self.assertEqual(int(histogram["conteo"].sum()), len(frame))
        self.assertTrue((histogram["conteo"] >= 10).all())
        self.assertLessEqual(len(histogram), 22)
        self.assertIn(" M", histogram["intervalo"].iloc[1])

    def test_log_histogram_includes_zero_and_uses_aggregated_log_ranges(self) -> None:
        positive = np.geomspace(1_000_000, 1_000_000_000, 500)
        frame = pd.DataFrame({"capital": np.concatenate([np.zeros(100), positive])})

        histogram = _log_histogram(frame, "capital")

        self.assertEqual(int(histogram["conteo"].sum()), len(frame))
        self.assertEqual(histogram["intervalo"].iloc[0], "Capital = 0")
        self.assertTrue((histogram["conteo"] >= 10).all())
        self.assertTrue(all(" M" in label for label in histogram["intervalo"].iloc[1:]))

    def test_coverage_bands_follow_requested_thresholds(self) -> None:
        frame = pd.DataFrame(
            {
                "capital": [25, 50, 80, 100, 0],
                "capital_necesario_sm": [100, 100, 100, 100, 0],
            }
        )

        result = coverage_band(frame)

        self.assertEqual(
            result.astype(str).tolist(),
            ["< 0.5", "0.5 a < 0.8", "0.8 a < 1", ">= 1", "No calculable"],
        )

    def test_quality_and_categorical_summaries_are_aggregated(self) -> None:
        frame = pd.DataFrame(
            {
                "edad": [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, None],
                "riesgo": ["A"] * 9 + ["B", None],
            }
        )

        overview = overview_table(frame)
        categories = safe_category_counts(frame, "riesgo", minimum_group_size=2)
        figures = completeness_figures(frame)

        self.assertAlmostEqual(
            overview.loc[overview["variable"] == "edad", "porcentaje_nulos"].iloc[0],
            100 / 11,
        )
        self.assertEqual(int(categories["registros"].sum()), len(frame))
        self.assertEqual(set(figures), {"completitud", "matriz_nulos"})
        self.assertEqual(
            len(figures["matriz_nulos"].data[0].z),
            len(frame.columns),
        )
        matrix_values = np.asarray(figures["matriz_nulos"].data[0].z)
        matrix_counts = np.asarray(figures["matriz_nulos"].data[0].customdata)
        self.assertTrue(np.isnan(matrix_values[0, 1]))
        self.assertTrue(np.isnan(matrix_counts[0, 1]))

    def test_distribution_charts_contain_aggregate_counts(self) -> None:
        frame = pd.DataFrame({"edad": np.tile(np.arange(20, 70), 4)})

        figures = distribution_figures(frame, "edad")

        self.assertEqual(set(figures), {"histograma", "densidad", "boxplot"})
        bar = figures["histograma"].data[0]
        self.assertEqual(sum(bar.y), len(frame))
        self.assertFalse(figures["boxplot"].data[0].boxpoints)

    def test_financial_histograms_use_categorical_ranges_not_log_axis(self) -> None:
        frame = pd.DataFrame(
            {
                "capital": np.concatenate(
                    [np.zeros(50), np.linspace(1_000_000, 100_000_000, 500)]
                )
            }
        )

        figures = distribution_figures(frame, "capital", logarithmic=True)

        self.assertIsNone(figures["histograma"].layout.xaxis.type)
        self.assertIsNone(figures["histograma_log"].layout.xaxis.type)
        self.assertEqual(sum(figures["histograma"].data[0].y), len(frame))
        self.assertEqual(sum(figures["histograma_log"].data[0].y), len(frame))
        self.assertIn("intervalos lineales", figures["histograma"].layout.title.text)
        self.assertIn("logarítmico", figures["histograma_log"].layout.title.text)

    def test_outlier_summary_does_not_return_individual_rows(self) -> None:
        frame = pd.DataFrame({"capital": [1.0] * 19 + [1_000_000.0]})

        result = iqr_outlier_summary(frame, ["capital"])

        self.assertEqual(result["extremos_iqr"].iloc[0], 1)
        self.assertNotIn("valor", result.columns)
        self.assertEqual(len(result), 1)

    def test_interpretations_cover_distributions_categories_and_associations(self) -> None:
        frame = pd.DataFrame(
            {
                "edad": np.tile(np.arange(20, 70), 4),
                "expectativa_vida": np.tile(np.arange(80, 30, -1), 4),
                "capital": np.linspace(1_000_000, 100_000_000, 200),
                "capital_necesario_sm": np.linspace(2_000_000, 200_000_000, 200),
                "descapitalizado": ["Sí"] * 40 + ["No"] * 160,
                "desfinanciado": ["Sí"] * 50 + ["No"] * 150,
                "riesgo": ["VEJEZ"] * 120 + ["GPM"] * 80,
                "riesgo_3": ["VEJEZ"] * 100 + ["GPM"] * 100,
                "sexo": ["F"] * 110 + ["M"] * 90,
            }
        )
        distribution = distribution_figures(frame, "edad")
        categorical = categorical_figures(frame, "riesgo")
        relationship = binned_relationship(
            frame, "edad", "expectativa_vida", "Edad vs expectativa"
        )
        self.assertIsNotNone(relationship)

        checks = (
            _chart_interpretation(frame, "edad_histograma", distribution["histograma"]),
            _chart_interpretation(frame, "riesgo_barras", categorical["barras"]),
            _chart_interpretation(
                frame, "relacion_edad_expectativa_vida", relationship
            ),
        )

        for interpretation in checks:
            self.assertGreaterEqual(len(interpretation), 1)
            self.assertTrue(all(interpretation))
            self.assertNotIn("Este gráfico es descriptivo", " ".join(interpretation))

    def test_dashboard_renders_interpretation_for_each_chart(self) -> None:
        frame = pd.DataFrame(
            {
                "edad": np.tile(np.arange(20, 70), 4),
                "expectativa_vida": np.tile(np.arange(80, 30, -1), 4),
                "capital": np.linspace(1_000_000, 100_000_000, 200),
                "capital_necesario_sm": np.linspace(2_000_000, 200_000_000, 200),
                "descapitalizado": ["Sí"] * 40 + ["No"] * 160,
                "desfinanciado": ["Sí"] * 50 + ["No"] * 150,
                "riesgo": ["VEJEZ"] * 120 + ["GPM"] * 80,
                "riesgo_3": ["VEJEZ"] * 100 + ["GPM"] * 100,
                "sexo": ["F"] * 110 + ["M"] * 90,
            }
        )
        figure = distribution_figures(frame, "edad")["histograma"]

        dashboard = build_dashboard_html(
            frame,
            {"edad_histograma": figure, "edad_boxplot": distribution_figures(frame, "edad")["boxplot"]},
        )

        self.assertEqual(dashboard.count('aria-label="Interpretación estadística"'), 2)
        self.assertIn("Mediana", dashboard)
        self.assertIn("no representa tasas de mortalidad", dashboard)


if __name__ == "__main__":
    unittest.main()
