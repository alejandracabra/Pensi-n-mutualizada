"""Índice de suficiencia de capital y escenarios determinísticos de selección."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.visualization.palette import (
    PLOTLY_TEMPLATE,
    SURA_ACCENT,
    SURA_DARK,
    SURA_LIME,
    SURA_PRIMARY,
    SURA_SECONDARY,
)

DEFAULT_ISC_THRESHOLDS = (1.00, 1.05, 1.10, 1.15, 1.20)
ISC_REQUIRED_COLUMNS = ("capital_mas_bono", "capital_necesario_sm", "edad", "riesgo")
NON_APPLICABLE_RISKS = frozenset({"GPM", "SUSTITUCION - GPM"})


def calculate_isc(frame: pd.DataFrame) -> pd.DataFrame:
    """Calcula ISC = (capital + bono) / capital necesario para 1 SM.

    El cociente se calcula cuando ambos importes son válidos y el denominador
    es positivo. La clasificación derivada solo aplica al universo en que la
    fuente reporta descapitalización; GPM y Sustitución-GPM se marcan no aplicables.
    """
    missing_columns = [column for column in ISC_REQUIRED_COLUMNS if column not in frame]
    if missing_columns:
        raise ValueError(
            "Faltan columnas requeridas para calcular el ISC: "
            + ", ".join(missing_columns)
        )

    result = frame.copy()
    capital = pd.to_numeric(result["capital_mas_bono"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    required = pd.to_numeric(
        result["capital_necesario_sm"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    age = pd.to_numeric(result["edad"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    risk = result["riesgo"].astype("string").str.strip().str.upper()
    applicable = ~risk.isin(NON_APPLICABLE_RISKS) & risk.notna()

    valid_denominator = required.where(required > 0)
    isc = capital.div(valid_denominator).replace([np.inf, -np.inf], np.nan)
    result["capital_mas_bono"] = capital
    result["capital_necesario_sm"] = required
    result["edad"] = age
    result["ISC"] = isc
    result["isc_aplicable"] = applicable.astype(bool)
    result["descapitalizada_calc"] = (
        isc.lt(1).where(isc.notna() & applicable).astype("boolean")
    )
    return result


def calculate_eligibility_scenarios(
    frame: pd.DataFrame,
    thresholds: Sequence[float] = DEFAULT_ISC_THRESHOLDS,
) -> pd.DataFrame:
    """Resume registros candidatos con ISC bajo cada umbral en el universo aplicable."""
    if "ISC" not in frame:
        raise ValueError("Calcule primero el ISC con calculate_isc().")
    required_columns = {"capital_mas_bono", "capital_necesario_sm", "edad", "isc_aplicable"}
    if not required_columns.issubset(frame.columns):
        raise ValueError(
            "Calcule primero el ISC aplicable a partir de capital_mas_bono, "
            "capital_necesario_sm y riesgo."
        )
    if not thresholds:
        raise ValueError("Debe proporcionarse al menos un umbral de ISC.")

    normalized_thresholds = [float(value) for value in thresholds]
    if any(not np.isfinite(value) or value <= 0 for value in normalized_thresholds):
        raise ValueError("Todos los umbrales de ISC deben ser positivos y finitos.")
    if normalized_thresholds != sorted(set(normalized_thresholds)):
        raise ValueError("Los umbrales deben ser únicos y estar en orden ascendente.")

    isc = pd.to_numeric(frame["ISC"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    capital = pd.to_numeric(frame["capital_mas_bono"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    required = pd.to_numeric(
        frame["capital_necesario_sm"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    age = pd.to_numeric(frame["edad"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    applicable = frame["isc_aplicable"].fillna(False).astype(bool)
    valid_isc = isc.notna() & applicable
    total_applicable = int(applicable.sum())
    total_records = len(frame)
    rows: list[dict[str, int | float]] = []

    for threshold in normalized_thresholds:
        eligible = valid_isc & isc.lt(threshold)
        cohort_capital = capital.loc[eligible]
        cohort_required = required.loc[eligible]
        cohort_age = age.loc[eligible]
        capital_total = float(cohort_capital.sum(min_count=1))
        required_total = float(cohort_required.sum(min_count=1))
        gap = required_total - capital_total

        rows.append(
            {
                "Umbral_ISC": threshold,
                "N_candidatos": int(eligible.sum()),
                "Pct_universo_aplicable": (
                    float(eligible.sum() / total_applicable * 100)
                    if total_applicable
                    else 0.0
                ),
                "Pct_registros_base": (
                    float(eligible.sum() / total_records * 100) if total_records else 0.0
                ),
                "Capital_mas_bono_total": capital_total,
                "Capital_SM_requerido": required_total,
                "Brecha_capital_requerido": gap,
                "Cobertura_agregada": (
                    capital_total / required_total if required_total > 0 else np.nan
                ),
                "Edad_media": (
                    float(cohort_age.mean()) if cohort_age.notna().any() else np.nan
                ),
                "N_edades_observadas": int(cohort_age.notna().sum()),
            }
        )

    return pd.DataFrame(rows)


def isc_data_quality(frame: pd.DataFrame) -> dict[str, int]:
    """Resume ISC calculable, universo aplicable y reproducción de la bandera fuente."""
    if "ISC" not in frame:
        raise ValueError("Calcule primero el ISC con calculate_isc().")

    capital = pd.to_numeric(frame["capital_mas_bono"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    required = pd.to_numeric(
        frame["capital_necesario_sm"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    isc = pd.to_numeric(frame["ISC"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    applicable = frame["isc_aplicable"].fillna(False).astype(bool)
    diagnostics = {
        "registros_base": int(len(frame)),
        "isc_calculable": int(isc.notna().sum()),
        "isc_no_calculable": int(isc.isna().sum()),
        "isc_aplicable": int(applicable.sum()),
        "riesgo_no_aplicable": int((~applicable).sum()),
        "capital_mas_bono_faltante_o_invalido": int(capital.isna().sum()),
        "capital_sm_faltante_o_invalido": int(required.isna().sum()),
        "capital_sm_no_positivo": int(required.le(0).sum()),
    }
    if "descapitalizacion" in frame:
        observed_flag = pd.to_numeric(
            frame["descapitalizacion"], errors="coerce"
        ).gt(0)
        calculated_flag = frame["descapitalizada_calc"].astype("boolean")
        comparable = applicable & calculated_flag.notna()
        diagnostics["clasificacion_comparable"] = int(comparable.sum())
        diagnostics["coincidencias_clasificacion"] = int(
            calculated_flag.loc[comparable].astype(bool)
            .eq(observed_flag.loc[comparable])
            .sum()
        )
        diagnostics["diferencias_clasificacion"] = (
            diagnostics["clasificacion_comparable"]
            - diagnostics["coincidencias_clasificacion"]
        )
        observed_amount = pd.to_numeric(
            frame["descapitalizacion"], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        expected_amount = (required - capital).clip(lower=0).where(applicable, 0)
        amount_comparable = observed_amount.notna() & expected_amount.notna()
        diagnostics["monto_descapitalizacion_comparable"] = int(
            amount_comparable.sum()
        )
        diagnostics["monto_descapitalizacion_coincide"] = int(
            np.isclose(
                observed_amount.loc[amount_comparable],
                expected_amount.loc[amount_comparable],
                rtol=1e-8,
                atol=0.01,
            ).sum()
        )
    if "capital_necesario_def" in frame and "desfinanciacion" in frame:
        required_def = pd.to_numeric(
            frame["capital_necesario_def"], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        observed_amount = pd.to_numeric(
            frame["desfinanciacion"], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        expected_amount = (required_def - capital).clip(lower=0).where(applicable, 0)
        amount_comparable = observed_amount.notna() & expected_amount.notna()
        diagnostics["monto_desfinanciacion_comparable"] = int(
            amount_comparable.sum()
        )
        diagnostics["monto_desfinanciacion_coincide"] = int(
            np.isclose(
                observed_amount.loc[amount_comparable],
                expected_amount.loc[amount_comparable],
                rtol=1e-8,
                atol=0.01,
            ).sum()
        )
    return diagnostics


def eligibility_figures(scenarios: pd.DataFrame) -> dict[str, go.Figure]:
    """Grafica registros candidatos y agregados de capital + bono por umbral."""
    if scenarios.empty:
        return {}

    threshold_labels = [f"< {threshold:.2f}" for threshold in scenarios["Umbral_ISC"]]
    counts = scenarios["N_candidatos"].astype(int)
    count_figure = go.Figure()
    count_figure.add_trace(
        go.Bar(
            x=threshold_labels,
            y=counts,
            name="Registros candidatos",
            marker_color=SURA_PRIMARY,
            customdata=scenarios[["Pct_universo_aplicable", "Pct_registros_base"]].to_numpy(),
            hovertemplate=(
                "Criterio: ISC %{x}<br>Registros candidatos: %{y:,}"
                "<br>% del universo aplicable: %{customdata[0]:.1f}%"
                "<br>% del total de registros: %{customdata[1]:.1f}%<extra></extra>"
            ),
        )
    )
    count_figure.add_trace(
        go.Scatter(
            x=threshold_labels,
            y=scenarios["Pct_universo_aplicable"],
            name="% del universo aplicable",
            mode="lines+markers",
            line={"color": SURA_SECONDARY, "width": 3},
            marker={"size": 9},
            yaxis="y2",
            hovertemplate="%{x}<br>% universo aplicable: %{y:.1f}%<extra></extra>",
        )
    )
    count_figure.update_layout(
        title="Escenarios de registros candidatos por umbral de ISC",
        xaxis_title="Criterio en el universo aplicable (ISC estrictamente menor que el umbral)",
        yaxis={"title": "Registros candidatos"},
        yaxis2={
            "title": "% del universo aplicable bajo el umbral",
            "overlaying": "y",
            "side": "right",
            "range": [0, 100],
        },
        template=PLOTLY_TEMPLATE,
        legend={"orientation": "h", "y": 1.12},
    )

    capital_figure = make_subplots(specs=[[{"secondary_y": True}]])
    capital_figure.add_trace(
        go.Bar(
            x=threshold_labels,
            y=scenarios["Capital_mas_bono_total"] / 1e12,
            name="Capital + bono disponible agregado",
            marker_color=SURA_PRIMARY,
            hovertemplate="%{x}<br>Capital + bono disponible: %{y:.2f} billones<extra></extra>",
        ),
        secondary_y=False,
    )
    capital_figure.add_trace(
        go.Bar(
            x=threshold_labels,
            y=scenarios["Capital_SM_requerido"] / 1e12,
            name="Capital requerido agregado",
            marker_color=SURA_ACCENT,
            hovertemplate="%{x}<br>Capital requerido: %{y:.2f} billones<extra></extra>",
        ),
        secondary_y=False,
    )
    capital_figure.add_trace(
        go.Scatter(
            x=threshold_labels,
            y=scenarios["Edad_media"],
            name="Edad media",
            mode="lines+markers",
            line={"color": SURA_DARK, "width": 3},
            marker={"color": SURA_LIME, "size": 9, "line": {"color": SURA_DARK, "width": 1}},
            hovertemplate="%{x}<br>Edad media: %{y:.1f} años<extra></extra>",
        ),
        secondary_y=True,
    )
    capital_figure.update_layout(
        title="Capital + bono disponible y requerido en registros candidatos",
        barmode="group",
        template=PLOTLY_TEMPLATE,
        legend={"orientation": "h", "y": 1.12},
    )
    capital_figure.update_xaxes(
        title_text="Criterio aplicado (ISC estrictamente menor que el umbral)"
    )
    capital_figure.update_yaxes(
        title_text="Capital + bono agregado (billones en unidades monetarias de la fuente)",
        secondary_y=False,
    )
    capital_figure.update_yaxes(
        title_text="Edad media (años)",
        secondary_y=True,
    )
    return {
        "isc_escenarios_registros": count_figure,
        "isc_escenarios_capital": capital_figure,
    }
