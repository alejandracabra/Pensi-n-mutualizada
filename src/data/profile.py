"""Perfilamiento descriptivo y medición de calidad de datos."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

IDENTIFIER_COLUMNS = {"registro", "numero_registro", "id"}
FINANCIAL_COLUMNS = (
    "capital",
    "capital_mas_bono",
    "capital_mes_anterior",
    "mesada",
    "capital_necesario_sm",
    "descapitalizacion",
    "desfinanciacion",
)
DEMOGRAPHIC_COLUMNS = ("edad", "expectativa_vida")
CATEGORICAL_COLUMNS = (
    "riesgo",
    "riesgo_3",
    "descapitalizado",
    "desfinanciado",
    "sexo",
)


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    """Devuelve variables numéricas excluyendo identificadores secuenciales."""
    return [
        column
        for column in frame.select_dtypes(include="number").columns
        if column not in IDENTIFIER_COLUMNS
    ]


def categorical_columns(frame: pd.DataFrame) -> list[str]:
    """Devuelve columnas de texto o categóricas."""
    return frame.select_dtypes(include=["object", "string", "category"]).columns.tolist()


def datetime_columns(frame: pd.DataFrame) -> list[str]:
    """Devuelve columnas de fecha y hora."""
    return frame.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()


def overview_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Resume tipo, completitud, cardinalidad y clasificación de cada variable."""
    rows = []
    for column in frame.columns:
        series = frame[column]
        if column in IDENTIFIER_COLUMNS:
            variable_type = "Identificador (excluido de métricas)"
        elif pd.api.types.is_datetime64_any_dtype(series):
            variable_type = "Fecha"
        elif pd.api.types.is_numeric_dtype(series):
            variable_type = "Numérica"
        else:
            variable_type = "Categórica"
        rows.append(
            {
                "variable": column,
                "tipo": variable_type,
                "registros_no_nulos": int(series.notna().sum()),
                "nulos": int(series.isna().sum()),
                "porcentaje_nulos": float(series.isna().mean() * 100),
                "valores_unicos": int(series.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)


def numeric_summary(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Calcula estadísticas y percentiles para columnas numéricas disponibles."""
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.DataFrame()
    percentiles = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
    result = frame[available].describe(percentiles=percentiles).T
    result.index.name = "variable"
    return result.reset_index()


def iqr_outlier_summary(
    frame: pd.DataFrame,
    columns: Iterable[str],
) -> pd.DataFrame:
    """Cuenta extremos según Tukey (1.5 IQR), sin exportar observaciones individuales."""
    rows: list[dict[str, object]] = []
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        spread = q3 - q1
        lower = q1 - 1.5 * spread
        upper = q3 + 1.5 * spread
        outside = (values < lower) | (values > upper)
        rows.append(
            {
                "variable": column,
                "limite_inferior_iqr": float(lower),
                "limite_superior_iqr": float(upper),
                "extremos_iqr": int(outside.sum()),
                "porcentaje_extremos": float(outside.mean() * 100),
            }
        )
    return pd.DataFrame(rows)


def safe_category_counts(
    frame: pd.DataFrame,
    column: str,
    minimum_group_size: int = 10,
) -> pd.DataFrame:
    """Resume categorías y combina grupos pequeños para evitar divulgar celdas raras."""
    if column not in frame.columns:
        return pd.DataFrame(columns=["categoria", "registros", "participacion_pct"])
    counts = frame[column].astype("string").fillna("Sin dato").value_counts(dropna=False)
    small_total = int(counts[counts < minimum_group_size].sum())
    counts = counts[counts >= minimum_group_size]
    if small_total:
        counts.loc["Otros / grupos pequeños"] = small_total
    result = counts.rename_axis("categoria").reset_index(name="registros")
    total = int(result["registros"].sum())
    result["participacion_pct"] = (
        result["registros"].div(total).mul(100) if total else 0.0
    )
    return result
