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
    completeness_figures,
    coverage_band,
    distribution_figures,
)


class ExplorationTests(unittest.TestCase):
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
        self.assertLessEqual(len(histogram), 42)

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

    def test_distribution_charts_contain_aggregate_counts(self) -> None:
        frame = pd.DataFrame({"edad": np.tile(np.arange(20, 70), 4)})

        figures = distribution_figures(frame, "edad")

        self.assertEqual(set(figures), {"histograma", "densidad", "boxplot"})
        bar = figures["histograma"].data[0]
        self.assertEqual(sum(bar.y), len(frame))
        self.assertFalse(figures["boxplot"].data[0].boxpoints)

    def test_outlier_summary_does_not_return_individual_rows(self) -> None:
        frame = pd.DataFrame({"capital": [1.0] * 19 + [1_000_000.0]})

        result = iqr_outlier_summary(frame, ["capital"])

        self.assertEqual(result["extremos_iqr"].iloc[0], 1)
        self.assertNotIn("valor", result.columns)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
