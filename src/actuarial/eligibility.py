"""Índice de suficiencia de capital y escenarios determinísticos de selección."""

from __future__ import annotations

from collections.abc import Sequence
import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.visualization.palette import (
    PLOTLY_TEMPLATE,
    SURA_ACCENT,
    SURA_DARK,
    SURA_LIME,
    SURA_PRIMARY,
    SURA_SECONDARY,
)

DEFAULT_ISC_THRESHOLDS = (1.00, 1.05, 1.10, 1.15, 1.20)
ISC_REQUIRED_COLUMNS = ("capital_mas_bono", "capital_necesario_sm", "riesgo")
from src.data.risk_catalog import (RiskCatalog, DEFAULT_CATALOG, PROVISIONAL_RISKS,
    EXCLUDED_RISKS, normalize_risk)
NON_APPLICABLE_RISKS = EXCLUDED_RISKS
DEFAULT_KNOWN_RISKS = PROVISIONAL_RISKS


def _catalog_for(frame, catalog=None, known_risks=None):
    if catalog is not None and known_risks is not None:
        raise ValueError("Especifique catálogo o known_risks, no ambos")
    if known_risks is not None:
        # API histórica: las exclusiones obligatorias nunca se reactivan.
        catalog=RiskCatalog(tuple((v,True) for v in sorted({normalize_risk(v) for v in known_risks}-EXCLUDED_RISKS-{''})))
    return catalog or frame.attrs.get('risk_catalog') or DEFAULT_CATALOG


def classified_isc(frame, catalog=None):
    """Recalcula únicamente con el catálogo adjunto; rechaza cambios implícitos."""
    previous=frame.attrs.get('risk_catalog')
    if previous is not None and catalog is not None and previous.fingerprint != catalog.fingerprint:
        raise ValueError("Catálogo distinto: reclasifique explícitamente con calculate_isc")
    return calculate_isc(frame,catalog=catalog)


def calculate_isc(frame: pd.DataFrame, known_risks=None, *, catalog: RiskCatalog | None = None) -> pd.DataFrame:
    """ISC financiero con catálogo explícito o heredado, nunca inferido de los datos."""
    catalog=_catalog_for(frame,catalog,known_risks)
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
    age = pd.to_numeric(result.get("edad", pd.Series(np.nan,index=result.index)), errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    classified=[catalog.classify(value) for value in result["riesgo"]]
    risk=pd.Series([v[0] for v in classified],index=result.index,dtype='string')
    status=pd.Series([v[1] for v in classified],index=result.index,dtype='string')
    applicable=status.eq('applicable')
    result["riesgo_normalizado"] = risk
    result["riesgo_estado"] = status
    result["riesgo_desconocido"] = status.eq('unknown')
    result["riesgo_faltante"] = status.eq('missing')
    result["capital_negativo"] = capital.lt(0)
    result["capital_invalido"] = capital.isna() | capital.lt(0)
    result["denominador_invalido"] = required.isna() | required.le(0)
    result["edad_invalida"] = age.isna() | ~age.between(0, 120)
    result["ISC_bruto"] = capital.div(required.where(required > 0)).replace([np.inf, -np.inf], np.nan)
    isc = result["ISC_bruto"].where(~result["capital_invalido"])
    result["capital_mas_bono"] = capital
    result["capital_necesario_sm"] = required
    result["edad"] = age
    result["ISC"] = isc
    result["isc_aplicable"] = applicable.astype(bool)
    result["descapitalizada_calc"] = (
        isc.lt(1).where(isc.notna() & applicable).astype("boolean")
    )
    result.attrs["risk_catalog"]=catalog
    return result


def calculate_eligibility_scenarios(
    frame: pd.DataFrame,
    thresholds: Sequence[float] = DEFAULT_ISC_THRESHOLDS,
    *, catalog: RiskCatalog | None = None,
) -> pd.DataFrame:
    """Resume registros candidatos con ISC bajo cada umbral en el universo aplicable."""
    frame=classified_isc(frame,catalog)
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


def isc_data_quality(frame: pd.DataFrame, *, catalog: RiskCatalog | None = None) -> dict[str, int]:
    """Resume ISC calculable, universo aplicable y reproducción de la bandera fuente."""
    frame=classified_isc(frame,catalog)
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
        "capital_negativo": int(capital.lt(0).sum()),
        "riesgo_desconocido": int(frame.get("riesgo_desconocido", pd.Series(False, index=frame.index)).sum()),
        "riesgo_faltante": int(frame.get("riesgo_faltante", pd.Series(False, index=frame.index)).sum()),
        "aplicable_calculable": int((applicable & isc.notna()).sum()),
    }
    if "descapitalizacion" in frame:
        observed_source = pd.to_numeric(frame["descapitalizacion"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        observed_flag = observed_source.gt(0)
        calculated_flag = frame["descapitalizada_calc"].astype("boolean")
        comparable = applicable & calculated_flag.notna() & observed_source.notna()
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


def isc_universe_summary(frame: pd.DataFrame, *, catalog: RiskCatalog | None = None) -> pd.DataFrame:
    """Partición exhaustiva: no aplicable, no calculable, ISC < 1, ISC >= 1."""
    calculated = classified_isc(frame,catalog)
    applicable = calculated["isc_aplicable"]
    valid = calculated["ISC"].notna()
    masks = {
        "No aplicable": ~applicable,
        "Aplicable sin ISC calculable": applicable & ~valid,
        "Descapitalizada (ISC < 1)": applicable & valid & calculated["ISC"].lt(1),
        "No descapitalizada (ISC >= 1)": applicable & valid & calculated["ISC"].ge(1),
    }
    return pd.DataFrame({"grupo": list(masks), "registros": [int(m.sum()) for m in masks.values()]})


def eligibility_figures(scenarios: pd.DataFrame) -> dict[str, go.Figure]:
    """Un concepto por gráfico, sin ejes dobles. Grupos acumulados, no elegibilidad."""
    if scenarios.empty:
        return {}
    labels = [f"< {t:.2f}" for t in scenarios["Umbral_ISC"]]
    counts = go.Figure(go.Bar(x=labels, y=scenarios["N_candidatos"],
        marker_color=SURA_PRIMARY, customdata=scenarios[["Pct_universo_aplicable"]],
        hovertemplate="ISC %{x}<br>Registros: %{y}<br>% aplicable: %{customdata[0]:.1f}%<extra></extra>"))
    counts.update_layout(title="Grupos exploratorios acumulados por umbral ISC",
        xaxis_title="ISC estrictamente menor que el umbral", yaxis_title="Registros", template=PLOTLY_TEMPLATE)
    capital = go.Figure()
    for column, label, color in [("Capital_mas_bono_total", "Capital + bono", SURA_PRIMARY),
                                  ("Capital_SM_requerido", "Requerimiento individual agregado", SURA_SECONDARY)]:
        capital.add_bar(x=labels, y=scenarios[column] / 1e12, name=label, marker_color=color)
    capital.update_layout(title="Capital disponible y requerimiento individual agregado",
        xaxis_title="ISC estrictamente menor que el umbral", yaxis_title="Billones de unidades monetarias de la fuente",
        barmode="group", template=PLOTLY_TEMPLATE)
    return {"isc_escenarios_registros": counts, "isc_escenarios_capital": capital}


def build_isc_cohorts(frame: pd.DataFrame, known_risks=None, *, catalog: RiskCatalog | None = None) -> dict[str, pd.DataFrame]:
    """A–E acumulativas; adicional [1,1.2). No determina elegibilidad.

    Registro debe identificar una persona/observación sin duplicados; si no
    existe se exige índice único. No deduplica ni elige arbitrariamente saldos.
    """
    if "registro" in frame:
        if frame["registro"].isna().any() or frame["registro"].duplicated().any():
            raise ValueError("registro faltante o duplicado: resolver unidad de análisis")
    elif not frame.index.is_unique:
        raise ValueError("Índice duplicado: resolver unidad de análisis")
    catalog=_catalog_for(frame,catalog,known_risks)
    calculated = classified_isc(frame,catalog)
    valid = calculated["isc_aplicable"] & calculated["ISC"].notna()
    groups = {name: calculated.loc[valid & calculated["ISC"].lt(t)].copy()
              for name, t in zip("ABCDE", DEFAULT_ISC_THRESHOLDS)}
    groups["adicional"] = calculated.loc[valid & calculated["ISC"].ge(1) & calculated["ISC"].lt(1.2)].copy()
    return groups


def describe_isc_cohorts(cohorts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Estadísticas de registros sin exportar observaciones individuales."""
    rows = []
    for name, frame in cohorts.items():
        row = {"cohort": name, "records": len(frame), "kind": "excluyente respecto A" if name == "adicional" else "acumulativa"}
        for col in ("edad", "capital_mas_bono", "capital_necesario_sm"):
            values = pd.to_numeric(frame[col], errors="coerce")
            for stat in ("count", "mean", "median", "min", "max", "sum"):
                row[f"{col}_{stat}"] = getattr(values, stat)()
        rows.append(row)
    return pd.DataFrame(rows)


def reconcile_isc(frame: pd.DataFrame, *, catalog: RiskCatalog | None = None) -> pd.DataFrame:
    """Indicadores jerárquicos: solo los cuatro estados de riesgo son partición."""
    frame=classified_isc(frame,catalog)
    applicable=frame.isc_aplicable
    valid=frame.ISC.notna()
    counts={
        'total':len(frame),
        'excluded_by_rule':int(frame.riesgo_estado.eq('excluded').sum()),
        'unknown_risk':int(frame.riesgo_estado.eq('unknown').sum()),
        'missing_risk':int(frame.riesgo_estado.eq('missing').sum()),
        'applicable':int(applicable.sum()),
        'applicable_calculable':int((applicable & valid).sum()),
        'applicable_not_calculable':int((applicable & ~valid).sum()),
        'isc_below_one':int((applicable & valid & frame.ISC.lt(1)).sum()),
        'isc_at_least_one':int((applicable & valid & frame.ISC.ge(1)).sum())}
    assert counts['total']==sum(counts[k] for k in ('excluded_by_rule','unknown_risk','missing_risk','applicable'))
    assert counts['applicable']==counts['applicable_calculable']+counts['applicable_not_calculable']
    assert counts['applicable_calculable']==counts['isc_below_one']+counts['isc_at_least_one']
    return pd.DataFrame({'indicator':list(counts),'records':list(counts.values())})


def compare_historical_counts(frame: pd.DataFrame, expected: dict) -> pd.DataFrame:
    """Referencias suministradas por el usuario, jamás constantes de clasificación."""
    actual=reconcile_isc(frame).set_index('indicator').records
    rows=[]
    for key,value in expected.items():
        if key not in actual or not isinstance(value,int) or value<0:
            raise ValueError('Referencia histórica inválida')
        observed=int(actual[key])
        rows.append(dict(indicator=key,expected=value,observed=observed,difference=observed-value,
            alert=observed!=value,diagnosis='Revisar catálogo/versiones, faltantes, calidad y unidad de análisis' if observed!=value else 'Coincide'))
    return pd.DataFrame(rows)
