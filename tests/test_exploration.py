"""Pruebas unitarias del cargador y las visualizaciones EDA."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.loader import find_workbook, normalize_columns
from src.actuarial.eligibility import (
    calculate_eligibility_scenarios,
    calculate_isc,
    eligibility_figures,
    isc_data_quality,
)
from src.data.profile import iqr_outlier_summary, overview_table, safe_category_counts
from src.visualization.eda import (
    _histogram,
    _log_histogram,
    binned_relationship,
    categorical_figures,
    completeness_figures,
    coverage_band,
    distribution_figures,
    financial_status_histograms,
)
from src.visualization.executive import build_executive_charts, generate_executive_package
from src.visualization.palette import SURA_FONT_FAMILY, SURA_PALETTE
from src.utils.reporting import (
    _chart_interpretation,
    _isc_scenarios_html,
    build_dashboard_html,
)


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

    def test_isc_and_nested_eligibility_scenarios(self) -> None:
        frame = pd.DataFrame(
            {
                "capital_mas_bono": [10, 50, 80, 100, 0, 10],
                "capital_necesario_sm": [100, 100, 100, 100, 0, np.nan],
                "capital_necesario_def": [100, 100, 100, 100, 0, np.nan],
                "edad": [60, 61, 62, 63, 64, np.nan],
                "riesgo": ["VEJEZ", "VEJEZ", "VEJEZ", "VEJEZ", "VEJEZ", "GPM"],
                "descapitalizacion": [90, 50, 20, 0, 0, 0],
                "desfinanciacion": [90, 50, 20, 0, 0, 0],
            }
        )
        original = frame.copy(deep=True)

        calculated = calculate_isc(frame)
        scenarios = calculate_eligibility_scenarios(
            calculated, thresholds=[1.0, 1.05, 1.1]
        )
        diagnostics = isc_data_quality(calculated)

        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(calculated["ISC"].iloc[:4].tolist(), [0.1, 0.5, 0.8, 1.0])
        self.assertTrue(calculated["descapitalizada_calc"].iloc[:3].all())
        self.assertFalse(calculated["descapitalizada_calc"].iloc[3])
        self.assertTrue(pd.isna(calculated["descapitalizada_calc"].iloc[4]))
        self.assertTrue(pd.isna(calculated["descapitalizada_calc"].iloc[5]))
        self.assertEqual(scenarios["N_candidatos"].tolist(), [3, 4, 4])
        self.assertEqual(
            scenarios["Pct_universo_aplicable"].tolist(), [60.0, 80.0, 80.0]
        )
        self.assertEqual(scenarios["Capital_mas_bono_total"].tolist(), [140.0, 240.0, 240.0])
        self.assertEqual(scenarios["Capital_SM_requerido"].tolist(), [300.0, 400.0, 400.0])
        self.assertEqual(scenarios["Brecha_capital_requerido"].tolist(), [160.0, 160.0, 160.0])
        self.assertEqual(scenarios["N_edades_observadas"].tolist(), [3, 4, 4])
        self.assertEqual(diagnostics["isc_calculable"], 4)
        self.assertEqual(diagnostics["isc_no_calculable"], 2)
        self.assertEqual(diagnostics["isc_aplicable"], 5)
        self.assertEqual(diagnostics["riesgo_no_aplicable"], 1)
        self.assertEqual(diagnostics["coincidencias_clasificacion"], 4)
        self.assertEqual(diagnostics["diferencias_clasificacion"], 0)
        self.assertEqual(diagnostics["monto_descapitalizacion_coincide"], 6)
        self.assertEqual(diagnostics["monto_desfinanciacion_coincide"], 6)

    def test_isc_rejects_missing_columns_and_invalid_thresholds(self) -> None:
        with self.assertRaisesRegex(ValueError, "Faltan columnas"):
            calculate_isc(pd.DataFrame({"capital": [10]}))

        valid = calculate_isc(
            pd.DataFrame(
                {
                    "capital_mas_bono": [10],
                    "capital_necesario_sm": [20],
                    "edad": [60],
                    "riesgo": ["VEJEZ"],
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "únicos"):
            calculate_eligibility_scenarios(valid, thresholds=[1.05, 1.0])
        with self.assertRaisesRegex(ValueError, "positivos y finitos"):
            calculate_eligibility_scenarios(valid, thresholds=[0])

    def test_isc_scenarios_render_table_and_figures(self) -> None:
        frame = calculate_isc(
            pd.DataFrame(
                {
                    "capital": [10, 50, 80, 100],
                    "capital_mas_bono": [10, 50, 80, 100],
                    "capital_necesario_sm": [100, 100, 100, 100],
                    "edad": [60, 61, 62, 63],
                    "riesgo": ["VEJEZ"] * 4,
                    "descapitalizacion": [90, 50, 20, 0],
                }
            )
        )
        scenarios = calculate_eligibility_scenarios(frame, [1.0, 1.1])
        diagnostics = isc_data_quality(frame)
        charts = eligibility_figures(scenarios)
        table_html = _isc_scenarios_html(scenarios, diagnostics)
        dashboard_html = build_dashboard_html(
            frame,
            charts,
            isc_scenarios=scenarios,
            isc_diagnostics=diagnostics,
        )

        self.assertEqual(set(charts), {"isc_escenarios_registros", "isc_escenarios_capital"})
        self.assertIn("ISC estrictamente menor", table_html)
        self.assertIn("Capital requerido agregado", table_html)
        self.assertIn("% total de registros", table_html)
        self.assertIn("capital_mas_bono", table_html)
        self.assertIn("4 coincidencias de 4", table_html)
        self.assertIn("no es una proyección", table_html)
        self.assertEqual(sum(charts["isc_escenarios_registros"].data[0].y), 7)
        self.assertIn(">3</td>", dashboard_html)
        self.assertIn("escenarios determinísticos por umbral", dashboard_html.lower())
        self.assertIn("No se usan rendimientos futuros ni se estiman probabilidades", dashboard_html)

    def test_executive_charts_use_exclusive_statuses_and_correct_isc_segments(self) -> None:
        rows = 30
        capital_available = [
            10, 20, 30, 40, 50, 60, 70, 80, 90,
            101, 102, 104, 106, 108, 111, 113, 116, 118,
            121, 131, 141, 151, 161, 171, 181, 191, 201, 211, 221, 231,
        ]
        frame = pd.DataFrame(
            {
                "capital": capital_available,
                "capital_mas_bono": capital_available,
                "capital_necesario_sm": np.full(rows, 100.0),
                "capital_necesario_def": np.full(rows, 120.0),
                "edad": np.arange(rows, dtype=float) + 50,
                "riesgo": ["VEJEZ"] * rows,
                "descapitalizado": ["Si"] * 9 + ["No"] * 21,
                "descapitalizacion": [1.0] * 9 + [0.0] * 21,
                "desfinanciado": ["Si"] * 12 + ["No"] * 18,
                "desfinanciacion": [1.0] * 12 + [0.0] * 18,
                "fecha_generacion": pd.to_datetime(["2026-08-24"] * rows),
            }
        )
        frame.loc[:8, "desfinanciado"] = "Si"
        frame.loc[:8, "desfinanciacion"] = 1.0
        frame.loc[9:11, "desfinanciado"] = "Si"
        frame.loc[9:11, "desfinanciacion"] = 1.0

        charts, scenarios, date_note = build_executive_charts(frame)

        self.assertEqual(len(charts), 6)
        self.assertIn("capitales positivos", charts[2].finding)
        self.assertIn("P99/P50", charts[2].finding)
        self.assertEqual(
            [int(patch.get_width()) for patch in charts[0].figure.axes[0].patches],
            [18, 3, 9],
        )
        self.assertEqual(
            scenarios["N_candidatos"].tolist(),
            [9, 12, 14, 16, 18],
        )
        self.assertIn("no coincide", date_note)
        self.assertIn("no representa elegibilidad", charts[5].note.lower())

    def test_executive_package_exports_png_svg_html_and_summary(self) -> None:
        frame = pd.DataFrame(
            {
                "capital": [
                    10, 20, 30, 40, 50, 60, 70, 80, 90,
                    101, 102, 104, 106, 108, 111, 113, 116, 118,
                    121, 131, 141, 151, 161, 171, 181, 191, 201, 211, 221, 231,
                ],
                "capital_mas_bono": [
                    10, 20, 30, 40, 50, 60, 70, 80, 90,
                    101, 102, 104, 106, 108, 111, 113, 116, 118,
                    121, 131, 141, 151, 161, 171, 181, 191, 201, 211, 221, 231,
                ],
                "capital_necesario_sm": np.full(30, 100.0),
                "capital_necesario_def": np.full(30, 120.0),
                "edad": np.arange(30, dtype=float) + 50,
                "riesgo": ["VEJEZ"] * 30,
                "descapitalizado": ["Si"] * 9 + ["No"] * 21,
                "descapitalizacion": [1.0] * 9 + [0.0] * 21,
                "desfinanciado": ["Si"] * 12 + ["No"] * 18,
                "desfinanciacion": [1.0] * 12 + [0.0] * 18,
                "fecha_generacion": pd.to_datetime(["2026-08-24"] * 30),
            }
        )
        frame.loc[:8, "desfinanciado"] = "Si"
        frame.loc[:8, "desfinanciacion"] = 1.0
        frame.loc[9:11, "desfinanciado"] = "Si"
        frame.loc[9:11, "desfinanciacion"] = 1.0

        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = generate_executive_package(
                frame, temporary_directory, source_name="fixture.xlsx"
            )
            figures = list(paths["figures_dir"].glob("*.png"))
            vectors = list(paths["figures_dir"].glob("*.svg"))
            figure_sizes = [path.stat().st_size for path in figures]
            figure_dimensions = [
                struct.unpack(">II", path.read_bytes()[16:24]) for path in figures
            ]
            html_report = paths["html"].read_text(encoding="utf-8")
            summary = paths["summary_markdown"].read_text(encoding="utf-8")

        self.assertEqual(len(figures), 6)
        self.assertEqual(len(vectors), 6)
        self.assertTrue(all(size > 5_000 for size in figure_sizes))
        self.assertTrue(all(size == (4000, 2250) for size in figure_dimensions))
        self.assertIn("Visualizaciones ejecutivas", html_report)
        self.assertIn("Distribución de edades", summary)

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

    def test_financial_status_histograms_compare_aggregated_capital(self) -> None:
        frame = pd.DataFrame(
            {
                "capital": np.concatenate(
                    [np.linspace(1_000_000, 30_000_000, 60), np.linspace(5_000_000, 90_000_000, 60)]
                ),
                "descapitalizado": ["No"] * 60 + ["Si"] * 60,
                "desfinanciado": ["No"] * 70 + ["Si"] * 50,
            }
        )

        figures = financial_status_histograms(frame)

        self.assertEqual(
            set(figures),
            {"capital_por_descapitalizado", "capital_por_desfinanciado"},
        )
        for name, figure in figures.items():
            self.assertEqual(figure.layout.barmode, "group")
            self.assertEqual(sum(sum(trace.y) for trace in figure.data), len(frame))
            self.assertTrue(all(count >= 10 for trace in figure.data for count in trace.y))
            interpretation = _chart_interpretation(frame, name, figure)
            self.assertTrue(any("Mediana del capital" in note for note in interpretation))
            self.assertTrue(any("no implica causalidad" in note for note in interpretation))

        missing_capital = frame.assign(capital=np.nan)
        self.assertEqual(financial_status_histograms(missing_capital), {})

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
