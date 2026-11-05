"""Construcción de KPIs y reportes reproducibles en Markdown y HTML."""

from __future__ import annotations

from src.actuarial.eligibility import isc_universe_summary

import html
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from src.data.profile import (
    CATEGORICAL_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    FINANCIAL_COLUMNS,
    categorical_columns,
    datetime_columns,
    iqr_outlier_summary,
    numeric_columns,
    numeric_summary,
    overview_table,
    safe_category_counts,
)
from src.visualization.eda import coverage_band
from src.visualization.palette import (
    SURA_DARK,
    SURA_FONT_FAMILY,
    SURA_LIGHT,
    SURA_PLOTLY_FONT,
    SURA_PRIMARY,
    SURA_SECONDARY,
)


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _is_affirmative(value: Any) -> bool:
    normalized = str(value).strip().lower()
    return normalized in {"si", "sí", "s", "true", "1", "yes", "y"}


def _affirmative_rate(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame:
        return None
    values = frame[column].dropna()
    if values.empty:
        return None
    return float(values.map(_is_affirmative).mean() * 100)


def calculate_kpis(frame: pd.DataFrame) -> dict[str, int | float | None]:
    """Calcula indicadores del EDA; no interpreta la cobertura como solvencia actuarial."""
    result: dict[str, int | float | None] = {
        "registros": int(len(frame)),
        "variables": int(frame.shape[1]),
        "edad_promedio": None,
        "edad_mediana": None,
        "expectativa_vida_promedio": None,
        "capital_promedio": None,
        "capital_mediano": None,
        "porcentaje_descapitalizado": _affirmative_rate(frame, "descapitalizado"),
        "porcentaje_desfinanciado": _affirmative_rate(frame, "desfinanciado"),
    }
    for column, keys, operation in (
        ("edad", ("edad_promedio", "edad_mediana"), ("mean", "median")),
        ("expectativa_vida", ("expectativa_vida_promedio",), ("mean",)),
        ("capital", ("capital_promedio", "capital_mediano"), ("mean", "median")),
    ):
        values = _number(frame, column)
        for key, method in zip(keys, operation, strict=True):
            result[key] = float(getattr(values, method)()) if not values.empty else None
    return result


def _format_number(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "No disponible"
    return f"{value:,.{decimals}f}"


def _format_money(value: float) -> str:
    """Formatea importes sin asumir moneda, pues depende de los metadatos de origen."""
    absolute_value = abs(value)
    if absolute_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f} mil millones"
    if absolute_value >= 1_000_000:
        return f"{value / 1_000_000:,.2f} millones"
    if absolute_value >= 1_000:
        return f"{value / 1_000:,.2f} mil"
    return f"{value:,.2f}"


def _variable_label(column: str) -> str:
    """Proporciona una etiqueta legible para nombres normalizados de variables."""
    return column.replace("_", " ")


def _association_strength(value: float) -> str:
    """Clasifica magnitudes de correlación como guía descriptiva, no inferencial."""
    magnitude = abs(value)
    if magnitude < 0.1:
        return "prácticamente nula"
    if magnitude < 0.3:
        return "débil"
    if magnitude < 0.5:
        return "moderada"
    if magnitude < 0.7:
        return "marcada"
    return "fuerte"


def _spearman_correlation(pair: pd.DataFrame, x_column: str, y_column: str) -> float:
    """Calcula Spearman como Pearson sobre rangos, evitando dependencias de scipy."""
    ranked = pair[[x_column, y_column]].rank(method="average")
    return float(ranked[x_column].corr(ranked[y_column]))


def _distribution_statistics(frame: pd.DataFrame, column: str) -> pd.Series:
    return _number(frame, column)


def _describe_distribution(
    frame: pd.DataFrame,
    column: str,
    kind: str,
    figure: go.Figure,
) -> list[str]:
    """Interpreta distribución, forma, dispersión y extremos de una variable."""
    values = _distribution_statistics(frame, column)
    if values.empty:
        return [f"No hay observaciones numéricas válidas para { _variable_label(column) }."]

    sample_size = len(values)
    missing_count = len(frame) - sample_size
    median = float(values.median())
    q1, q3 = (float(value) for value in values.quantile([0.25, 0.75]))
    mean = float(values.mean())
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = int(((values < lower_fence) | (values > upper_fence)).sum())
    variable = _variable_label(column)
    is_financial = column in FINANCIAL_COLUMNS

    def format_value(value: float) -> str:
        return _format_money(value) if is_financial else _format_number(value)

    notes = [
        f"Base efectiva: {sample_size:,} valores válidos"
        + (f" y {missing_count:,} no disponibles." if missing_count else "."),
    ]

    if kind in {"histograma", "histograma_log"} and figure.data:
        trace = figure.data[0]
        counts = np.asarray(trace.y, dtype=float)
        labels = [str(label) for label in trace.x]
        if counts.size and counts.sum() > 0:
            largest = int(np.argmax(counts))
            share = counts[largest] / counts.sum() * 100
            notes.append(
                f"El intervalo con mayor frecuencia es «{labels[largest]}» "
                f"({counts[largest]:,.0f}; {share:.1f}% de los válidos)."
            )
        if not is_financial:
            notes.append(
                f"Mediana {format_value(median)}; el 50% central se ubica entre "
                f"{format_value(q1)} y {format_value(q3)}."
            )
        if kind == "histograma_log":
            positive_share = float((values > 0).mean() * 100)
            notes.append(
                f"El {positive_share:.1f}% tiene saldo positivo. Los rangos positivos "
                "son geométricos y el cero se presenta aparte: el eje X es categórico, "
                "por lo que no se deben comparar las distancias visuales entre barras."
            )
        elif is_financial:
            notes.append(
                f"El 1.er cuartil es {format_value(q1)} y el 3.er cuartil "
                f"{format_value(q3)}; el 50% central abarca ese intervalo."
            )
    elif kind == "densidad":
        density = np.asarray(figure.data[0].y, dtype=float) if figure.data else np.array([])
        locations = np.asarray(figure.data[0].x, dtype=float) if figure.data else np.array([])
        if density.size and locations.size:
            mode = float(locations[int(np.nanargmax(density))])
            notes.append(
                f"La mayor concentración suavizada se ubica cerca de "
                f"{format_value(mode)}. Es una densidad aproximada construida con "
                "intervalos agregados, no un estimador KDE sobre observaciones individuales."
            )
        notes.append(
            "La curva describe la distribución marginal y no ajusta por edad, sexo, "
            "riesgo ni otras covariables."
        )
    elif kind == "boxplot":
        notes.append(
            f"Mediana {format_value(median)}; rango intercuartílico "
            f"{format_value(q1)}–{format_value(q3)} "
            f"(IQR {format_value(iqr)}). Se identifican {outliers:,} valores fuera "
            "de las cercas de Tukey (1.5 × IQR); son alertas para revisión, no errores confirmados."
        )
    elif kind == "violin":
        skew = "media mayor que mediana" if mean > median else "media menor que mediana"
        notes.append(
            f"Mediana {format_value(median)}; IQR {format_value(q1)}–{format_value(q3)}. "
            f"La {skew} ({format_value(mean)} frente a {format_value(median)}), "
            "lo que sugiere asimetría que debe leerse junto con la escala del gráfico."
        )
        notes.append(
            "El ancho del violín aproxima la densidad desde intervalos agregados; "
            "no representa microdatos ni una estimación no paramétrica exacta."
        )
    else:
        skewness = float(values.skew()) if sample_size > 2 else 0.0
        if abs(skewness) >= 0.5:
            shape = "asimetría a la derecha" if skewness > 0 else "asimetría a la izquierda"
        else:
            shape = "asimetría muestral reducida"
        notes.append(
            f"Media {format_value(mean)} y mediana {format_value(median)}; "
            f"{shape} (asimetría de Fisher {skewness:.2f}). "
            f"Fuera de las cercas de Tukey: {outliers:,} ({outliers / sample_size:.1%})."
        )
        if is_financial:
            notes.append(
                "La interpretación monetaria requiere confirmar moneda y fecha de valoración "
                "en el diccionario de datos."
            )

    if column in {"expectativa_vida"}:
        notes.append(
            "La expectativa registrada es una variable descriptiva de la fuente; "
            "no equivale a una curva de supervivencia ni a una tabla de mortalidad validada."
        )
    return notes


def _describe_categorical(frame: pd.DataFrame, column: str, kind: str) -> list[str]:
    """Resume concentración y denominador de una variable categórica."""
    summary = safe_category_counts(frame, column)
    valid_count = int(frame[column].notna().sum())
    missing_count = int(frame[column].isna().sum())
    if summary.empty or valid_count == 0:
        return [f"No hay categorías observadas para {_variable_label(column)}."]

    top = summary.iloc[0]
    distinct_count = int(frame[column].nunique(dropna=True))
    notes = [
        f"Categoría principal: «{top['categoria']}», {int(top['registros']):,} registros "
        f"({top['participacion_pct']:.1f}% de los registros, incluidos faltantes en el denominador "
        "del resumen)."
    ]
    denominator = valid_count + missing_count
    notes.append(
        f"Categorías observadas: {distinct_count:,}; válidos: {valid_count:,}; "
        f"faltantes: {missing_count:,} ({missing_count / denominator:.1%}). "
        "La participación es descriptiva y depende de la codificación y definición de negocio."
    )
    if kind == "sunburst":
        notes.append(
            "El área representa participación relativa: el gráfico no implica jerarquía "
            "causal ni transición entre categorías."
        )
    return notes


def _describe_association(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    logarithmic_x: bool = False,
    logarithmic_y: bool = False,
) -> list[str]:
    """Interpreta la asociación monotónica y disponibilidad de un par numérico."""
    if x_column not in frame or y_column not in frame:
        return ["No están disponibles ambas variables para calcular la relación."]
    pair = frame[[x_column, y_column]].apply(pd.to_numeric, errors="coerce")
    pair = pair.replace([np.inf, -np.inf], np.nan).dropna()
    initial_count = len(pair)
    if logarithmic_x:
        pair = pair[pair[x_column] > 0]
    if logarithmic_y:
        pair = pair[pair[y_column] > 0]
    if len(pair) < 2:
        return ["No hay suficientes pares válidos para resumir la asociación."]

    rho = _spearman_correlation(pair, x_column, y_column)
    direction = "positiva" if rho > 0 else "negativa" if rho < 0 else "nula"
    notes = [
        f"Se muestran {len(pair):,} pares completos"
        + (
            f" de {initial_count:,} pares completos antes del filtro de valores positivos."
            if logarithmic_x or logarithmic_y
            else "."
        ),
        f"Asociación monotónica de Spearman ρ = {rho:.2f} "
        f"({direction}, magnitud {_association_strength(rho)}). "
        "Describe asociación, no causalidad."
    ]
    if logarithmic_x or logarithmic_y:
        filtered_variables = [
            _variable_label(column)
            for column, condition in (
                (x_column, logarithmic_x),
                (y_column, logarithmic_y),
            )
            if condition
        ]
        notes.append(
            "La relación se calcula tras excluir valores no positivos de "
            + ", ".join(filtered_variables)
            + " para permitir representación logarítmica; no resume a quienes tienen saldo cero."
        )
    if column_is_financial(x_column) or column_is_financial(y_column):
        notes.append(
            "La posible asimetría y los valores extremos pueden afectar la lectura; "
            "contraste los agregados visuales con percentiles y definiciones de negocio."
        )
    return notes


def column_is_financial(column: str) -> bool:
    """Indica si una variable pertenece al conjunto monetario del EDA."""
    return column in FINANCIAL_COLUMNS


def _chart_interpretation(
    frame: pd.DataFrame,
    name: str,
    figure: go.Figure,
    isc_scenarios: pd.DataFrame | None = None,
    isc_diagnostics: dict[str, int] | None = None,
) -> list[str]:
    """Asigna una lectura estadística breve a cada gráfico del dashboard."""
    status_histogram_columns = {
        "capital_por_descapitalizado": "descapitalizado",
        "capital_por_desfinanciado": "desfinanciado",
    }
    if name in status_histogram_columns:
        status_column = status_histogram_columns[name]
        if status_column not in frame or "capital" not in frame:
            return ["No están disponibles el capital y el estado financiero para interpretar este gráfico."]
        capital = _number(frame, "capital")
        status = frame.loc[capital.index, status_column].astype("string").fillna("Sin dato")
        count_by_status = status.value_counts()
        median_by_status = capital.groupby(status).median()
        notes = [
            f"Capital disponible válido en {len(capital):,} registros; "
            f"{len(frame) - len(capital):,} se excluyen por capital faltante o no numérico."
        ]
        if not count_by_status.empty:
            largest_group = str(count_by_status.index[0])
            notes.append(
                f"El grupo más numeroso es «{largest_group}» "
                f"({int(count_by_status.iloc[0]):,} registros). "
                "Las barras muestran conteos por intervalos de capital compartidos."
            )
        if len(median_by_status) >= 2:
            medians = median_by_status.sort_values()
            low_group, high_group = str(medians.index[0]), str(medians.index[-1])
            notes.append(
                f"Mediana del capital: «{low_group}» = {_format_money(float(medians.iloc[0]))}; "
                f"«{high_group}» = {_format_money(float(medians.iloc[-1]))}. "
                "La diferencia es descriptiva y no implica causalidad."
            )
        notes.append(
            "Los extremos se combinan con los intervalos de borde y las celdas pequeñas "
            "se agrupan para evitar mostrar grupos con menos de 10 registros."
        )
        return notes

    if name in {"isc_escenarios_registros", "isc_escenarios_capital"}:
        if isc_scenarios is None or isc_scenarios.empty:
            return ["No se proporcionó una tabla de escenarios ISC para interpretar este gráfico."]
        first = isc_scenarios.iloc[0]
        last = isc_scenarios.iloc[-1]
        additional = int(last["N_candidatos"] - first["N_candidatos"])
        baseline = int(first["N_candidatos"])
        notes = [
            f"Con ISC < {first['Umbral_ISC']:.2f} hay {baseline:,} registros candidatos "
            f"({first['Pct_universo_aplicable']:.1f}% del universo aplicable). "
            f"Al ampliar el umbral a {last['Umbral_ISC']:.2f}, se incluyen "
            f"{int(last['N_candidatos']):,}; son {additional:,} registros adicionales."
        ]
        if name == "isc_escenarios_capital":
            notes.append(
                f"En el escenario ISC < {last['Umbral_ISC']:.2f}, el capital + bono "
                f"agregado es {_format_money(float(last['Capital_mas_bono_total']))} y la suma del "
                f"capital requerido individual para 1 SM es "
                f"{_format_money(float(last['Capital_SM_requerido']))}."
            )
        notes.append(
            "ISC = capital_mas_bono / capital_necesario_sm. Se excluyen GPM y "
            "SUSTITUCION - GPM porque la clasificación fuente no los marca como "
            "descapitalizados. Estos conteos son escenarios por umbral, no una validación "
            "de elegibilidad ni probabilidades. El capital requerido es el valor "
            "actuarial observado en la fuente; no se recalcula ni se proyecta."
        )
        if isc_diagnostics:
            notes.append(
                f"Universo aplicable: {isc_diagnostics['isc_aplicable']:,}; "
                f"no aplicables: {isc_diagnostics['riesgo_no_aplicable']:,}. "
                f"ISC no calculable: {isc_diagnostics['isc_no_calculable']:,}."
            )
            if "diferencias_clasificacion" in isc_diagnostics:
                notes.append(
                    f"Con ISC < 1,00 se reproducen "
                    f"{isc_diagnostics['coincidencias_clasificacion']:,} de "
                    f"{isc_diagnostics['clasificacion_comparable']:,} clasificaciones "
                    "observadas en el universo aplicable."
                )
        return notes

    if name == "completitud":
        missing = frame.isna().mean().mul(100)
        ranked = missing.sort_values(ascending=False)
        nonzero = ranked[ranked > 0]
        if nonzero.empty:
            return ["No se observan valores faltantes en las variables representadas."]
        top = nonzero.head(3)
        detail = "; ".join(f"{column}: {value:.1f}%" for column, value in top.items())
        complete_rows = int(frame.notna().all(axis=1).sum())
        return [
            f"Mayor faltante por variable: {detail}. La completitud total por fila es "
            f"{complete_rows / max(len(frame), 1):.1%} ({complete_rows:,} de {len(frame):,}).",
            "Los faltantes pueden reflejar reglas de aplicabilidad estructural (p. ej., "
            "beneficiarios opcionales), no necesariamente errores; investigue su mecanismo antes de imputar."
        ]

    if name == "matriz_nulos":
        mask = frame.isna().astype(np.uint8)
        counts = mask.T @ mask
        columns = list(frame.columns)
        pairs = [
            (int(counts.loc[left, right]), left, right)
            for index, left in enumerate(columns)
            for right in columns[index + 1 :]
            if counts.loc[left, right] >= 10
        ]
        if not pairs:
            return [
                "No hay pares de variables con al menos 10 registros simultáneamente faltantes.",
                "La matriz muestra proporción conjunta de nulos sobre el total de registros; "
                "celdas con conteo menor que 10 se suprimen."
            ]
        count, left, right = max(pairs)
        return [
            f"Mayor co-ocurrencia entre variables distintas: {left} y {right}, "
            f"{count:,} filas ({count / max(len(frame), 1):.1%} del total).",
            "Es una proporción conjunta sobre toda la base, no una correlación ni una prueba "
            "del mecanismo de ausencia; las celdas con menos de 10 casos se suprimen."
        ]

    if name == "cobertura":
        bands = coverage_band(frame)
        calculable = bands[bands != "No calculable"]
        if calculable.empty:
            return ["No hay casos con capital necesario positivo y ambos importes disponibles."]
        below_one = calculable.isin(["< 0.5", "0.5 a < 0.8", "0.8 a < 1"])
        notes = [
            f"Cobertura calculable en {len(calculable):,} de {len(frame):,} registros "
            f"({len(calculable) / max(len(frame), 1):.1%}). "
            f"De ellos, {below_one.mean():.1%} tiene capital inferior al requerido "
            "según esta comparación individual."
        ]
        counts = bands.value_counts()
        top_band = str(counts.index[0])
        notes.append(
            f"Banda más frecuente: «{top_band}» ({int(counts.iloc[0]):,} registros). "
            "Es una razón de capitales descriptiva; no incorpora flujos futuros, "
            "supervivencia, rentabilidad, gastos ni mutualización, y no mide solvencia actuarial."
        )
        notes.append(
            "Esta cobertura usa capital sin Bono y abarca todos los riesgos; no equivale "
            "al indicador oficial de descapitalización, que en esta base se reproduce "
            "con capital_mas_bono y excluye GPM y Sustitución-GPM."
        )
        return notes

    if name == "correlaciones_financieras":
        columns = [column for column in FINANCIAL_COLUMNS if column in frame]
        correlation = frame[columns].apply(pd.to_numeric, errors="coerce").corr()
        pairs = [
            (abs(float(correlation.loc[left, right])), float(correlation.loc[left, right]), left, right)
            for index, left in enumerate(columns)
            for right in columns[index + 1 :]
            if pd.notna(correlation.loc[left, right])
        ]
        if not pairs:
            return ["No se calcularon correlaciones para las variables financieras disponibles."]
        _, value, left, right = max(pairs)
        notes = [
            f"Mayor correlación lineal de Pearson entre variables distintas: "
            f"{_variable_label(left)} y {_variable_label(right)}, r = {value:.2f} "
            f"({_association_strength(value)} en magnitud)."
        ]
        notes.append(
            "Pearson mide asociación lineal y es sensible a asimetría, valores extremos "
            "y saldos cero; no implica causalidad ni equivalencia entre medidas de capital."
        )
        return notes

    if name in {"sunburst_riesgos", "treemap_riesgos"}:
        risk = frame.get("riesgo", pd.Series(dtype="string")).astype("string").fillna("Sin dato")
        risk3 = frame.get("riesgo_3", pd.Series(dtype="string")).astype("string").fillna("Sin dato")
        counts = pd.DataFrame({"riesgo": risk, "riesgo_3": risk3}).value_counts()
        if counts.empty:
            return ["No hay categorías de riesgo disponibles para este gráfico."]
        (top_risk, top_risk3), top_count = counts.index[0], int(counts.iloc[0])
        top_risk_share = risk.value_counts(normalize=True).iloc[0] * 100
        return [
            f"La combinación más frecuente es «{top_risk} / {top_risk3}» "
            f"({top_count:,} registros; {top_count / max(len(frame), 1):.1%} del total).",
            f"La categoría principal de Riesgo concentra {top_risk_share:.1f}%. "
            "El área representa conteos agregados; Riesgo 3 es una clasificación, "
            "no una transición temporal inferida."
        ]

    relationship_map = {
        "relacion_edad_expectativa_vida": ("edad", "expectativa_vida", False, False),
        "relacion_edad_capital": ("edad", "capital", False, True),
        "relacion_capital_descapitalizacion": ("capital", "descapitalizacion", True, False),
        "relacion_capital_necesario_sm_capital": (
            "capital_necesario_sm",
            "capital",
            True,
            True,
        ),
    }
    if name in relationship_map:
        x_column, y_column, log_x, log_y = relationship_map[name]
        return _describe_association(
            frame,
            x_column,
            y_column,
            logarithmic_x=log_x,
            logarithmic_y=log_y,
        )

    if name == "matriz_relaciones":
        columns = [
            column
            for column in ("edad", "expectativa_vida", "capital", "capital_necesario_sm")
            if column in frame
        ]
        pairs = []
        for index, left in enumerate(columns):
            for right in columns[index + 1 :]:
                pair = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) >= 2:
                    rho = _spearman_correlation(pair, left, right)
                    pairs.append((abs(rho), rho, left, right, len(pair)))
        if not pairs:
            return ["No hay suficientes pares completos para resumir las relaciones."]
        _, rho, left, right, count = max(pairs)
        return [
            f"Entre las relaciones fuera de la diagonal, la asociación monotónica de mayor "
            f"magnitud es {_variable_label(left)}–{_variable_label(right)} "
            f"(Spearman ρ = {rho:.2f}; n = {count:,}).",
            "La diagonal resume distribuciones marginales; las demás celdas muestran conteos "
            "en intervalos. Las celdas con menos de 10 casos se ocultan y no hay ajuste causal."
        ]

    if name.startswith("violin_"):
        column = name.removeprefix("violin_")
        return _describe_distribution(frame, column, "violin", figure)

    for column in sorted(
        set((*DEMOGRAPHIC_COLUMNS, *FINANCIAL_COLUMNS)),
        key=len,
        reverse=True,
    ):
        prefix = f"{column}_"
        if name.startswith(prefix):
            kind = name.removeprefix(prefix)
            if kind in {"histograma", "histograma_log", "densidad", "boxplot"}:
                return _describe_distribution(frame, column, kind, figure)

    for column in CATEGORICAL_COLUMNS:
        prefix = f"{column}_"
        if name.startswith(prefix):
            return _describe_categorical(
                frame,
                column,
                name.removeprefix(prefix),
            )

    return [
        "Este gráfico es descriptivo y resume los datos mostrados; interprete sus escalas, "
        "denominador y supuestos de agrupación antes de comparar subgrupos."
    ]


def _interpretation_html(notes: list[str]) -> str:
    """Renderiza notas estadísticas como HTML seguro, sin incorporar HTML de la fuente."""
    items = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
    return (
        '<aside class="interpretation" aria-label="Interpretación estadística">'
        "<h3>Interpretación estadística</h3>"
        f"<ul>{items}</ul></aside>"
    )


def _isc_scenarios_html(
    scenarios: pd.DataFrame,
    diagnostics: dict[str, int],
) -> str:
    """Renderiza resultados determinísticos ISC y su denominador en una tabla HTML."""
    columns = (
        ("Umbral_ISC", "Umbral ISC"),
        ("N_candidatos", "Registros candidatos"),
        ("Pct_universo_aplicable", "% universo aplicable"),
        ("Pct_registros_base", "% total de registros"),
        ("Capital_mas_bono_total", "Capital + bono agregado"),
        ("Capital_SM_requerido", "Capital requerido agregado (1 SM)"),
        ("Brecha_capital_requerido", "Brecha agregada requerida - disponible"),
        ("Edad_media", "Edad media (años)"),
    )
    headers = "".join(f"<th scope=\"col\">{html.escape(label)}</th>" for _, label in columns)
    body_rows = []
    for _, row in scenarios.iterrows():
        cells = []
        for key, _ in columns:
            value = row[key]
            if key == "Umbral_ISC":
                formatted = f"{value:.2f}"
            elif key == "N_candidatos":
                formatted = f"{int(value):,}"
            elif key in {"Pct_universo_aplicable", "Pct_registros_base"}:
                formatted = f"{value:.1f}%"
            elif key in {
                "Capital_mas_bono_total",
                "Capital_SM_requerido",
                "Brecha_capital_requerido",
            }:
                formatted = _format_money(float(value))
            else:
                formatted = _format_number(value, decimals=1)
            cells.append(f"<td>{html.escape(formatted)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return f"""
<section class="summary isc-scenarios">
  <h2>ISC y escenarios determinísticos por umbral</h2>
  <p><strong>Definición:</strong> ISC = (capital + bono) / capital necesario para 1 SM.
  Cada fila selecciona registros con ISC estrictamente menor que el umbral indicado.
  No se usan rendimientos futuros ni se estiman probabilidades.</p>
  <p><strong>Base:</strong> {diagnostics['registros_base']:,} registros; ISC calculable en
  {diagnostics['isc_calculable']:,}; no calculable en {diagnostics['isc_no_calculable']:,}.
  Universo aplicable: {diagnostics['isc_aplicable']:,}; no aplicables:
  {diagnostics['riesgo_no_aplicable']:,} (Riesgo GPM y Sustitución-GPM, que la clasificación
  fuente no marca como descapitalizados). Los no calculables se excluyen. Los conteos
  corresponden a registros de la hoja, no necesariamente a afiliados únicos.</p>
  {f"<p>Validación contra Descapitalización observada: {diagnostics['coincidencias_clasificacion']:,} coincidencias de {diagnostics['clasificacion_comparable']:,} registros aplicables con ISC calculable; {diagnostics['diferencias_clasificacion']:,} diferencias.</p>" if 'diferencias_clasificacion' in diagnostics else ""}
  {f"<p>Contraste de importes de la hoja, aplicando la regla observada (universo aplicable: brecha positiva; GPM y Sustitución-GPM: cero): Descapitalización coincide con max(capital_necesario_sm - capital_mas_bono, 0) en {diagnostics['monto_descapitalizacion_coincide']:,}/{diagnostics['monto_descapitalizacion_comparable']:,} registros; Desfinanciación coincide con max(capital_necesario_def - capital_mas_bono, 0) en {diagnostics['monto_desfinanciacion_coincide']:,}/{diagnostics['monto_desfinanciacion_comparable']:,}.</p>" if 'monto_desfinanciacion_coincide' in diagnostics and 'monto_descapitalizacion_coincide' in diagnostics else ""}
  <div class="table-scroll"><table><thead><tr>{headers}</tr></thead>
  <tbody>{"".join(body_rows)}</tbody></table></div>
  <p class="note">El capital disponible agregado suma capital_mas_bono observado.
  “Capital requerido agregado” suma capital_necesario_sm observado para
  los registros seleccionados; no es una proyección de obligaciones ni un pasivo actuarial
  de la bolsa. La brecha es requerido menos capital disponible y no considera flujos,
  mortalidad, rentabilidad, gastos, actualización del SMMLV ni mutualización.
  El Excel contiene valores, no las fórmulas del cálculo actuarial externo; este contraste
  no audita sus supuestos de beneficiarios ni expectativa de vida.</p>
</section>
"""


def _table_markdown(frame: pd.DataFrame, max_rows: int = 60) -> str:
    """Serializa tablas Markdown sin generar dependencias opcionales."""
    if frame.empty:
        return "_No hay variables disponibles para esta sección._"
    shown = frame.head(max_rows).copy()
    for column in shown.columns:
        if pd.api.types.is_numeric_dtype(shown[column]):
            shown[column] = shown[column].map(
                lambda value: "" if pd.isna(value) else f"{value:,.2f}"
            )
    headers = [str(column) for column in shown.columns]
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    rows.extend("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |" for row in shown.itertuples(index=False, name=None))
    if len(frame) > max_rows:
        rows.append(f"\n_Se muestran {max_rows} de {len(frame)} filas._")
    return "\n".join(rows)


def automatic_findings(frame: pd.DataFrame, kpis: dict[str, Any]) -> list[str]:
    """Redacta hallazgos descriptivos basados en reglas transparentes."""
    findings = [
        f"La base contiene {kpis['registros']:,} registros y {kpis['variables']} variables."
    ]
    missing = frame.isna().mean().mul(100).sort_values(ascending=False)
    missing_variables = missing[missing > 0]
    if missing_variables.empty:
        findings.append("No se observan valores nulos en las variables cargadas.")
    else:
        top = missing_variables.head(3)
        details = "; ".join(f"{name} ({value:.1f}%)" for name, value in top.items())
        findings.append(f"Las mayores proporciones de nulos corresponden a: {details}.")

    for key, label in (
        ("porcentaje_descapitalizado", "descapitalizados"),
        ("porcentaje_desfinanciado", "desfinanciados"),
    ):
        value = kpis[key]
        if value is not None:
            findings.append(f"El {value:.1f}% de los registros está clasificado como {label}.")

    coverage = coverage_band(frame)
    calculable = coverage[coverage != "No calculable"]
    if not calculable.empty:
        below = calculable.isin(["< 0.5", "0.5 a < 0.8", "0.8 a < 1"]).mean() * 100
        findings.append(
            f"Entre los registros con cobertura calculable, {below:.1f}% presenta "
            "capital (sin Bono) inferior al capital necesario para 1 SM. Esta cobertura "
            "global no equivale a la clasificación oficial de descapitalización."
        )
    findings.append(
        "La cobertura es un indicador exploratorio de suficiencia de capital individual; "
        "no incorpora supervivencia, rentabilidad, gastos, reglas de beneficio ni "
        "redistribución colectiva y no constituye una medida de solvencia."
    )
    return findings


def build_markdown_report(
    frame: pd.DataFrame,
    source_name: str,
    isc_scenarios: pd.DataFrame | None = None,
    isc_diagnostics: dict[str, int] | None = None,
) -> str:
    """Genera un informe técnico con tablas, KPIs y hallazgos automáticos."""
    overview = overview_table(frame)
    numeric = numeric_columns(frame)
    kpis = calculate_kpis(frame)
    demo = numeric_summary(frame, DEMOGRAPHIC_COLUMNS)
    financial = numeric_summary(frame, FINANCIAL_COLUMNS)
    outliers = iqr_outlier_summary(frame, [*DEMOGRAPHIC_COLUMNS, *FINANCIAL_COLUMNS])
    findings = automatic_findings(frame, kpis)
    financial_data_quality = pd.DataFrame(
        [
            {
                "variable": column,
                "registros_validos": int(_number(frame, column).size),
                "saldos_cero": int((_number(frame, column) == 0).sum()),
                "nulos": int(frame[column].isna().sum()),
            }
            for column in FINANCIAL_COLUMNS
            if column in frame
        ]
    )
    isc_section = ""
    if isc_scenarios is not None and not isc_scenarios.empty:
        scenario_table = isc_scenarios[
            [
                "Umbral_ISC",
                "N_candidatos",
                "Pct_universo_aplicable",
                "Pct_registros_base",
                "Capital_mas_bono_total",
                "Capital_SM_requerido",
                "Brecha_capital_requerido",
                "Edad_media",
            ]
        ].copy()
        isc_validation = ""
        if (
            isc_diagnostics is not None
            and "diferencias_clasificacion" in isc_diagnostics
        ):
            isc_validation = (
                "En el contraste de la hoja, la clasificación coincide con ISC < 1 "
                f"en {isc_diagnostics['coincidencias_clasificacion']:,}/"
                f"{isc_diagnostics['clasificacion_comparable']:,} registros aplicables. "
                "Aplicando la regla observada (universo aplicable: brecha positiva; "
                "GPM y Sustitución-GPM: cero), Descapitalización coincide con "
                "max(capital_necesario_sm - capital_mas_bono, 0) "
                f"en {isc_diagnostics.get('monto_descapitalizacion_coincide', 0):,}/"
                f"{isc_diagnostics.get('monto_descapitalizacion_comparable', 0):,} importes; "
                "Desfinanciación coincide con max(capital_necesario_def - capital_mas_bono, 0) "
                f"en {isc_diagnostics.get('monto_desfinanciacion_coincide', 0):,}/"
                f"{isc_diagnostics.get('monto_desfinanciacion_comparable', 0):,}. "
                "Esto valida los valores exportados, no el código externo que los produjo.\n\n"
            )
        isc_section = (
            "\n## ISC y escenarios determinísticos por umbral\n\n"
            "ISC = (capital_mas_bono) / capital_necesario_sm. Los escenarios seleccionan "
            "registros del universo aplicable (se excluyen Riesgo GPM y Sustitución-GPM, "
            "que la clasificación fuente no marca como descapitalizados) con ISC "
            "estrictamente menor que cada umbral. No son probabilidades ni una validación "
            "definitiva de elegibilidad. Los casos no calculables se excluyen. El capital "
            "requerido suma valores actuariales individuales observados en la base; no es "
            "un pasivo proyectado. Los conteos son registros, no necesariamente afiliados "
            "únicos. El Excel contiene valores exportados, no las fórmulas del cálculo "
            "actuarial externo; este informe no audita los supuestos de beneficiarios ni "
            "expectativa de vida. Valide estas reglas con el área dueña del cálculo.\n\n"
            "### Universo y clasificación ISC\n\n"
            f"{_table_markdown(isc_universe_summary(frame))}\n\n"
            f"Diagnóstico: {isc_diagnostics}.\n\n"
            f"{isc_validation}"
            f"{_table_markdown(scenario_table)}\n"
        )

    categorical_sections = []
    for column in CATEGORICAL_COLUMNS:
        if column in frame:
            counts = safe_category_counts(frame, column)
            categorical_sections.append(f"### {column}\n\n{_table_markdown(counts)}")

    kpi_lines = [
        f"- **Edad promedio:** {_format_number(kpis['edad_promedio'])} años.",
        f"- **Edad mediana:** {_format_number(kpis['edad_mediana'])} años.",
        f"- **Expectativa de vida promedio:** {_format_number(kpis['expectativa_vida_promedio'])} años.",
        f"- **Capital promedio:** ${_format_number(kpis['capital_promedio'])}.",
        f"- **Capital mediano:** ${_format_number(kpis['capital_mediano'])}.",
        f"- **Registros descapitalizados:** {_format_number(kpis['porcentaje_descapitalizado'])}%.",
        f"- **Registros desfinanciados:** {_format_number(kpis['porcentaje_desfinanciado'])}%.",
    ]
    return f"""# Análisis exploratorio de datos — Pensión mutualizada

> Informe generado automáticamente. Las cifras son descriptivas y dependen de la calidad y definiciones de la fuente; no constituyen una conclusión actuarial.

## Descripción de la base

- **Archivo fuente:** `{Path(source_name).name}` (se omite la ruta local).
- **Registros:** {len(frame):,}.
- **Variables:** {frame.shape[1]}.
- **Variables numéricas:** {len(numeric)}.
- **Variables categóricas:** {len(categorical_columns(frame))}.
- **Variables de fecha:** {len(datetime_columns(frame))}.

### Diccionario de tipos y completitud

{_table_markdown(overview)}

## Indicadores iniciales

{chr(10).join(kpi_lines)}

El dashboard interactivo complementario se genera en [`exploracion.html`](./exploracion.html).

## Calidad de datos

El porcentaje de nulos se calcula sobre los registros de la hoja cargada. Los extremos se identifican con la regla exploratoria de 1.5 veces el rango intercuartílico; no deben interpretarse automáticamente como errores.

### Variables con mayor proporción de nulos

{_table_markdown(overview.sort_values("porcentaje_nulos", ascending=False).query("porcentaje_nulos > 0").head(15))}

### Extremos estadísticos

{_table_markdown(outliers.sort_values("porcentaje_extremos", ascending=False))}

## Análisis demográfico

Estadísticas de edad y expectativa de vida, con percentiles 1, 5, 25, 50, 75, 95 y 99:

{_table_markdown(demo)}

## Análisis financiero

Las variables monetarias conservan las unidades y fecha de valoración de la fuente; valide la moneda antes de interpretar los valores. Los histogramas lineales usan intervalos de igual amplitud, y las versiones logarítmicas agrupan importes positivos en bandas base geométricas. Para evitar mostrar celdas con menos de 10 registros, se combinan bandas vecinas; por tanto, el ancho de los rangos finales puede variar. El eje X es categórico, no una escala logarítmica continua: las etiquetas muestran los límites monetarios de cada rango. Los saldos cero aparecen en una categoría separada y los valores nulos se excluyen del histograma; los conteos de las distribuciones se conservan en intervalos agregados.

{_table_markdown(financial)}

### Registros usados por los histogramas financieros

{_table_markdown(financial_data_quality)}

{isc_section}

## Análisis de riesgo y participación

{chr(10).join(categorical_sections)}

## Hallazgos principales

{chr(10).join(f"- {finding}" for finding in findings)}

## Limitaciones y uso responsable

- La clasificación de riesgo y de descapitalización se interpreta tal como está registrada; las definiciones de negocio requieren validación.
- El criterio IQR es una alerta exploratoria y no sustituye la revisión de calidad ni el conocimiento actuarial.
- Las estadísticas no modelan mortalidad, supervivencia, rentabilidad, indexación, gastos, beneficiarios ni obligaciones.
- No se exportan observaciones individuales a los gráficos. Aun así, revise la autorización y el riesgo de divulgación antes de compartir reportes.
"""


def _kpi_cards(kpis: dict[str, Any]) -> str:
    cards = (
        ("Registros", f"{kpis['registros']:,}"),
        ("Variables", f"{kpis['variables']:,}"),
        ("Edad promedio", f"{_format_number(kpis['edad_promedio'])} años"),
        ("Edad mediana", f"{_format_number(kpis['edad_mediana'])} años"),
        ("Expectativa de vida", f"{_format_number(kpis['expectativa_vida_promedio'])} años"),
        ("Capital promedio", f"${_format_number(kpis['capital_promedio'])}"),
        ("Capital mediano", f"${_format_number(kpis['capital_mediano'])}"),
        ("% descapitalizados", f"{_format_number(kpis['porcentaje_descapitalizado'])}%"),
        ("% desfinanciados", f"{_format_number(kpis['porcentaje_desfinanciado'])}%"),
    )
    return "\n".join(
        f'<article class="kpi"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></article>'
        for label, value in cards
    )


def _dashboard_filter(frame: pd.DataFrame) -> str:
    """Construye filtros accesibles sobre tabla agregada de riesgo y sexo."""
    group_columns = [column for column in ("riesgo", "sexo") if column in frame]
    if not group_columns:
        return "<p>No hay variables de riesgo o sexo para filtrar.</p>"
    grouped = frame.groupby(group_columns, dropna=False, observed=True).size().rename("registros").reset_index()
    grouped[group_columns] = grouped[group_columns].fillna("Sin dato")
    for column in ("riesgo", "sexo"):
        if column not in grouped:
            grouped[column] = "Todos"
    grouped = grouped.groupby(["riesgo", "sexo"], dropna=False, observed=True)["registros"].sum().reset_index()
    grouped.loc[grouped["registros"] < 10, "riesgo"] = "Otros / grupos pequeños"
    grouped.loc[grouped["registros"] < 10, "sexo"] = "Agrupado"
    grouped = grouped.groupby(["riesgo", "sexo"], observed=True)["registros"].sum().reset_index()
    records = grouped.to_json(orient="records", force_ascii=True).replace("<", "\\u003c")
    return f"""
<section class="filter-panel">
  <h2>Filtros de resumen</h2>
  <label for="filter-risk">Riesgo</label>
  <select id="filter-risk"><option value="">Todos</option></select>
  <label for="filter-sex">Sexo</label>
  <select id="filter-sex"><option value="">Todos</option></select>
  <p id="filter-result" aria-live="polite"></p>
  <div id="filter-chart" role="img" aria-label="Participación agregada según los filtros seleccionados"></div>
  <aside class="interpretation" aria-label="Interpretación estadística de los filtros">
    <h3>Interpretación estadística</h3>
    <p id="filter-interpretation" aria-live="polite"></p>
  </aside>
  <p class="note">La vista de participación responde a los filtros. Los demás gráficos resumen la población completa.</p>
</section>
<script id="aggregate-data" type="application/json">{records}</script>
<script>
(() => {{
  const rows = JSON.parse(document.getElementById("aggregate-data").textContent);
  const risk = document.getElementById("filter-risk");
  const sex = document.getElementById("filter-sex");
  const result = document.getElementById("filter-result");
  const interpretation = document.getElementById("filter-interpretation");
  const addOptions = (select, values) => [...new Set(values)].sort().forEach(value => {{
    const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option);
  }});
  addOptions(risk, rows.map(row => row.riesgo)); addOptions(sex, rows.map(row => row.sexo));
  const update = () => {{
    const selected = rows.filter(row => (!risk.value || row.riesgo === risk.value) && (!sex.value || row.sexo === sex.value));
    const count = selected.reduce((total, row) => total + row.registros, 0);
    result.textContent = `Registros en el filtro: ${{count.toLocaleString("es-CO")}}`;
    const share = rows.reduce((total, row) => total + row.registros, 0)
      ? count / rows.reduce((total, row) => total + row.registros, 0) * 100
      : 0;
    interpretation.textContent = `La selección reúne ${{count.toLocaleString("es-CO")}} registros (${{share.toFixed(1)}}% del total de esta vista agregada). El gráfico compara conteos de la dimensión restante; no representa tasas de mortalidad, probabilidades ni efectos causales.`;
    const dimension = risk.value ? "sexo" : "riesgo";
    const grouped = selected.reduce((totals, row) => {{
      totals[row[dimension]] = (totals[row[dimension]] || 0) + row.registros;
      return totals;
    }}, {{}});
    Plotly.react("filter-chart", [{{
      type: "bar",
      x: Object.keys(grouped),
      y: Object.values(grouped),
      marker: {{color: "{SURA_PRIMARY}"}},
      hovertemplate: "%{{x}}<br>Registros: %{{y:,}}<extra></extra>"
    }}], {{
      title: risk.value ? "Registros por sexo" : "Registros por riesgo",
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{family: "{SURA_PLOTLY_FONT}", color: "{SURA_DARK}"}},
      margin: {{t: 50, r: 20, b: 60, l: 60}},
      yaxis: {{title: "Registros"}}
    }}, {{responsive: true, displaylogo: false}});
  }};
  risk.addEventListener("change", update); sex.addEventListener("change", update); update();
}})();
</script>
"""


def build_dashboard_html(
    frame: pd.DataFrame,
    figures: dict[str, go.Figure],
    title: str = "Exploración de datos — Pensión mutualizada",
    isc_scenarios: pd.DataFrame | None = None,
    isc_diagnostics: dict[str, int] | None = None,
) -> str:
    """Genera un dashboard HTML autónomo con Plotly embebido y datos agregados."""
    kpis = calculate_kpis(frame)
    sections = []
    for index, (name, figure) in enumerate(figures.items()):
        div_id = f"eda-figure-{index}"
        chart_figure = go.Figure(figure)
        chart_figure.update_layout(
            font={"family": SURA_PLOTLY_FONT, "color": SURA_DARK},
            legend={"font": {"family": SURA_PLOTLY_FONT, "color": SURA_DARK}},
        )
        chart_figure.update_xaxes(
            tickfont={"family": SURA_PLOTLY_FONT, "color": SURA_DARK},
            title_font={"family": SURA_PLOTLY_FONT, "color": SURA_DARK},
        )
        chart_figure.update_yaxes(
            tickfont={"family": SURA_PLOTLY_FONT, "color": SURA_DARK},
            title_font={"family": SURA_PLOTLY_FONT, "color": SURA_DARK},
        )
        chart = pio.to_html(
            chart_figure,
            full_html=False,
            include_plotlyjs=False,
            div_id=div_id,
            config={"responsive": True, "displaylogo": False},
        )
        sections.append(
            f'<section class="chart"><h2>{html.escape(name.replace("_", " ").capitalize())}'
            f"</h2>{chart}{_interpretation_html(_chart_interpretation(frame, name, figure, isc_scenarios, isc_diagnostics))}</section>"
        )
    filter_panel = _dashboard_filter(frame)
    isc_table = (
        _isc_scenarios_html(isc_scenarios, isc_diagnostics)
        if isc_scenarios is not None
        and isc_diagnostics is not None
        and not isc_scenarios.empty
        else ""
    )
    findings = "".join(
        f"<li>{html.escape(text)}</li>" for text in automatic_findings(frame, kpis)
    )
    styles = f"""
    :root {{ --primary:{SURA_PRIMARY}; --secondary:{SURA_SECONDARY};
      --light:{SURA_LIGHT}; --dark:{SURA_DARK}; --accent:#4EC3E0;
      --lime:#E3E829; --yellow:#FFE946;
      --font-sura:{SURA_FONT_FAMILY}; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--dark); background:var(--light); font-family:var(--font-sura); }}
    header {{ padding:3rem max(1.5rem,calc((100vw - 1200px)/2)); color:white;
      background:linear-gradient(120deg,var(--dark),var(--secondary)); }}
    header h1 {{ margin:.2rem 0 1rem; max-width:900px; font-size:clamp(2rem,4vw,3rem); }}
    header p {{ max-width:850px; line-height:1.6; }}
    main {{ max-width:1200px; margin:2rem auto; padding:0 1rem; }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; }}
    .kpi,.chart,.filter-panel,.summary {{ background:white; border-radius:12px; padding:1.2rem;
      border:1px solid var(--accent); box-shadow:0 2px 12px rgba(0,51,160,.08); }}
    .table-scroll {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
    th,td {{ padding:.7rem; border-bottom:1px solid var(--accent); text-align:right; }}
    th {{ color:var(--primary); background:#eef7fa; }}
    th:first-child,td:first-child {{ text-align:left; }}
    .kpi span {{ display:block; color:var(--secondary); font-size:.9rem; }}
    .kpi strong {{ display:block; margin-top:.5rem; color:var(--dark); font-size:1.4rem; }}
    .chart,.filter-panel,.summary {{ margin-top:1.25rem; }}
    .chart h2 {{ color:var(--dark); font-size:1.15rem; font-weight:600; }}
    .interpretation {{ margin-top:1rem; padding:.9rem 1rem; border-left:4px solid var(--lime);
      border-radius:4px; background:#f6f8e8; color:var(--dark); line-height:1.5; }}
    .interpretation h3 {{ margin:0 0 .45rem; color:var(--primary); font-size:1rem; }}
    .interpretation ul {{ margin:.2rem 0 0; padding-left:1.25rem; }}
    .interpretation li + li {{ margin-top:.3rem; }}
    select {{ display:block; margin:.4rem 0 1rem; padding:.55rem; min-width:220px;
      color:var(--dark); border:1px solid var(--secondary); accent-color:var(--primary); }}
    .note {{ color:var(--secondary); font-size:.9rem; }}
    footer {{ padding:2rem 1rem; text-align:center; color:var(--dark); border-top:3px solid var(--lime); }}
    """
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Análisis exploratorio agregado de la base del proyecto de pensión mutualizada">
<title>{html.escape(title)}</title><style>{styles}</style><script>{get_plotlyjs()}</script></head><body>
<header><p>Protección · Investigación actuarial y estadística</p><h1>{html.escape(title)}</h1>
<p>Perfilamiento descriptivo inicial de afiliados y saldos. Los hallazgos no constituyen una evaluación de solvencia ni una recomendación de producto.</p></header>
<main><section><h2>Resumen ejecutivo</h2><p>Exploración de {kpis["registros"]:,} registros y {kpis["variables"]} variables. Los gráficos se construyen sobre agregados y estadísticas resumidas; no se incluyen observaciones individuales.</p>
<div class="kpis">{_kpi_cards(kpis)}</div></section>
{isc_table}
<section class="summary"><h2>Universo y clasificación ISC</h2>
<p>Partición del total de registros. ISC &lt; 1 clasifica descapitalización solo en el universo aplicable y calculable; los umbrales adicionales son exploratorios.</p>
{isc_universe_summary(frame).to_html(index=False, escape=True) if all(c in frame for c in ('capital_mas_bono', 'capital_necesario_sm', 'edad', 'riesgo')) else '<p>Faltan variables para clasificar el universo ISC.</p>'}</section>
{filter_panel}
<section class="summary"><h2>Conclusiones automáticas</h2><ul>{findings}</ul>
<p class="note">La cobertura experimental usa capital sin Bono / capital necesario para 1 SM y toda la base; no equivale a la clasificación oficial de descapitalización ni mide solvencia mutualizada.</p></section>
{"".join(sections)}</main>
<footer>Reporte generado localmente. Revise permisos de uso y confidencialidad antes de compartir este archivo.</footer>
</body></html>"""


def write_reports(
    frame: pd.DataFrame,
    figures: dict[str, go.Figure],
    source_name: str,
    reports_dir: str | Path,
    isc_scenarios: pd.DataFrame | None = None,
    isc_diagnostics: dict[str, int] | None = None,
) -> tuple[Path, Path]:
    """Guarda el informe HTML interactivo y el resumen técnico Markdown."""
    output = Path(reports_dir)
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / "exploracion.html"
    markdown_path = output / "exploracion.md"
    html_path.write_text(
        build_dashboard_html(
            frame,
            figures,
            isc_scenarios=isc_scenarios,
            isc_diagnostics=isc_diagnostics,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_markdown_report(
            frame,
            source_name,
            isc_scenarios=isc_scenarios,
            isc_diagnostics=isc_diagnostics,
        ),
        encoding="utf-8",
    )
    return html_path, markdown_path
