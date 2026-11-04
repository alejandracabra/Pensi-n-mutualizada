"""Executive-ready visualizations for the mutualized-pension EDA."""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullLocator

from src.actuarial.eligibility import (
    DEFAULT_ISC_THRESHOLDS,
    calculate_eligibility_scenarios,
    calculate_isc,
)
from src.data.loader import find_workbook, load_workbook

BLUE = "#0033A0"
YELLOW = "#FFE946"
CYAN = "#00AEC7"
LIGHT_BLUE = "#4EC3E0"
GRAY = "#667085"
LIGHT_GRAY = "#D9DEE7"
PALE_BLUE = "#EEF3FA"
WHITE = "#FFFFFF"
FONT = "Sura Sans"
FIGURE_SIZE = (40 / 3, 7.5)
DPI = 300


@dataclass(frozen=True)
class ExecutiveChart:
    """Figure plus its presentation metadata and interpretation."""

    key: str
    title: str
    objective: str
    variables: str
    population: str
    finding: str
    slide: str
    note: str
    figure: Figure


def _format_integer(value: int | float) -> str:
    """Format counts using Colombian separators."""
    return f"{int(value):,}".replace(",", ".")


def _format_decimal(value: float, decimals: int = 1) -> str:
    """Format decimals using Colombian separators."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_millions(value: float, decimals: int = 0) -> str:
    return f"${_format_decimal(value / 1_000_000, decimals)} M"


def _format_billions(value: float, decimals: int = 1) -> str:
    return f"{_format_decimal(value / 1_000_000_000_000, decimals)}"


def _clean_axis(ax: Axes, *, grid_axis: str | None = None) -> None:
    ax.set_facecolor(WHITE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LIGHT_GRAY)
    ax.spines["bottom"].set_color(LIGHT_GRAY)
    ax.tick_params(axis="both", colors=GRAY, labelsize=13, length=0, pad=8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=LIGHT_GRAY, linewidth=0.8, alpha=0.7)
        ax.set_axisbelow(True)


def _canvas(
    title: str,
    subtitle: str,
    note: str,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> tuple[Figure, Axes]:
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    fig.patch.set_facecolor(WHITE)
    fig.suptitle(
        title,
        x=0.075,
        y=0.94,
        ha="left",
        va="top",
        color=BLUE,
        fontsize=23,
        fontweight="bold",
        fontfamily=FONT,
    )
    fig.text(
        0.075,
        0.875,
        subtitle,
        ha="left",
        va="top",
        color=GRAY,
        fontsize=14,
        fontfamily=FONT,
    )
    fig.text(
        0.075,
        0.105,
        note,
        ha="left",
        va="bottom",
        color=GRAY,
        fontsize=10.5,
        fontfamily=FONT,
        wrap=True,
    )
    date_note = (
        f"Fuente: {source_name} · Corte informado: {cutoff} · "
        f"Máxima Fecha de Generación observada: {generation_max}"
    )
    fig.text(
        0.075,
        0.055,
        date_note,
        ha="left",
        va="bottom",
        color=GRAY,
        fontsize=9.5,
        fontfamily=FONT,
    )
    ax.set_position([0.13, 0.23, 0.80, 0.57])
    return fig, ax


def _applicable_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calculated = calculate_isc(frame)
    return calculated.loc[calculated["isc_aplicable"]].copy()


def _base_metadata(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
) -> tuple[str, str, int, int]:
    if "fecha_generacion" in frame and frame["fecha_generacion"].notna().any():
        generation_max = pd.to_datetime(
            frame["fecha_generacion"], errors="coerce"
        ).max().strftime("%d/%m/%Y")
    else:
        generation_max = "no disponible"
    if "fecha_generacion" in frame and generation_max != "no disponible":
        date_note = (
            f"La Fecha de Generación más reciente ({generation_max}) no coincide con "
            f"el corte informado ({cutoff}); confirmar si son fechas con distinto significado."
        )
    else:
        date_note = "La fecha de corte proviene del metadato informado para la base."
    applicable = _applicable_frame(frame)
    return (
        generation_max,
        date_note,
        len(frame),
        int(applicable["ISC"].notna().sum()),
    )


def _composition_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> ExecutiveChart:
    statuses = (
        frame["descapitalizado"].astype("string").fillna("Sin dato"),
        frame["desfinanciado"].astype("string").fillna("Sin dato"),
    )
    combinations = pd.DataFrame(
        {"descapitalizado": statuses[0], "desfinanciado": statuses[1]}
    ).value_counts(dropna=False)
    keys = [
        ("No", "No", "Sin descapitalización ni desfinanciación"),
        ("No", "Si", "Solo desfinanciado"),
        ("Si", "Si", "Descapitalizado y desfinanciado"),
    ]
    labels = [label for _, _, label in keys]
    counts = [int(combinations.get((left, right), 0)) for left, right, _ in keys]
    shares = [count / len(frame) * 100 for count in counts]
    fig, ax = _canvas(
        "Los estados financieros se superponen en 19.356 registros",
        "Composición mutuamente excluyente según las dos clasificaciones de la base",
        "La base no contiene casos «solo descapitalizado»: todos los descapitalizados también "
        "están marcados como desfinanciados. Cada registro aparece una sola vez.",
        source_name,
        cutoff,
        generation_max,
    )
    bars = ax.barh(
        labels,
        counts,
        color=[BLUE, GRAY, YELLOW],
        height=0.56,
        edgecolor="none",
    )
    ax.invert_yaxis()
    ax.set_xlim(0, max(counts) * 1.2)
    ax.set_xlabel("Registros", color=BLUE, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: _format_integer(value)))
    _clean_axis(ax, grid_axis="x")
    for bar, count, share in zip(bars, counts, shares, strict=True):
        ax.text(
            bar.get_width() + max(counts) * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{_format_integer(count)}  ·  {_format_decimal(share, 1)}%",
            va="center",
            ha="left",
            color=BLUE,
            fontsize=14,
            fontfamily=FONT,
            fontweight="bold",
        )
    return ExecutiveChart(
        key="01_composicion_poblacion",
        title="Composición de la población por estado financiero",
        objective="Mostrar los estados sin duplicar registros y hacer visible la superposición.",
        variables="Descapitalizado; Desfinanciado",
        population=f"Base completa: {_format_integer(len(frame))} registros",
        finding=(
            f"{_format_integer(counts[2])} ({_format_decimal(shares[2], 1)}%) tienen ambas "
            f"marcas; {_format_integer(counts[1])} ({_format_decimal(shares[1], 1)}%) solo "
            "desfinanciación; no hay casos solo descapitalizados."
        ),
        slide="1 · Universo y definiciones",
        note=(
            f"Universo: {_format_integer(len(frame))} registros. Las tres categorías son "
            "excluyentes y suman el universo."
        ),
        figure=fig,
    )


def _age_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> ExecutiveChart:
    applicable = _applicable_frame(frame)
    age = pd.to_numeric(applicable["edad"], errors="coerce")
    edges = np.arange(0, 131, 5)
    fig, ax = _canvas(
        "La mediana de edad es menor en las cuentas descapitalizadas",
        "Distribución porcentual de edades por clasificación de descapitalización",
        "Cada grupo se normaliza por su propio tamaño para comparar perfiles, no volúmenes. "
        "El universo aplicable sigue el criterio de riesgo observado en la base.",
        source_name,
        cutoff,
        generation_max,
    )
    colors = {"No": GRAY, "Si": BLUE}
    for value, label in (("No", "No descapitalizado"), ("Si", "Descapitalizado")):
        values = age.loc[applicable["descapitalizado"].eq(value) & age.notna()]
        weights = np.full(len(values), 100 / max(len(values), 1))
        ax.hist(
            values,
            bins=edges,
            weights=weights,
            histtype="step",
            linewidth=2.8,
            color=colors[value],
            label=f"{label} (n={_format_integer(len(values))})",
        )
    ax.set_xlim(0, 130)
    ax.set_xticks(np.arange(0, 131, 10))
    ax.set_xlabel("Edad (años)", color=BLUE, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.set_ylabel(
        "Registros dentro del estado (%)",
        color=BLUE,
        fontsize=14,
        fontfamily=FONT,
        labelpad=10,
    )
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{_format_decimal(value, 0)}%")
    )
    ax.legend(frameon=False, loc="upper left", fontsize=13)
    _clean_axis(ax, grid_axis="y")
    summary = applicable.assign(edad=age).groupby("descapitalizado")["edad"].median()
    finding = (
        f"Mediana de edad: {_format_decimal(float(summary.get('Si', np.nan)), 1)} años en "
        f"descapitalizados y {_format_decimal(float(summary.get('No', np.nan)), 1)} años "
        "en el resto del universo aplicable."
    )
    return ExecutiveChart(
        key="02_distribucion_edades",
        title="Distribución de edades",
        objective="Comparar el perfil etario de cuentas descapitalizadas y no descapitalizadas.",
        variables="Edad; Descapitalizado; Riesgo (aplicabilidad)",
        population=(
            f"Universo aplicable: {_format_integer(len(applicable))} registros; "
            f"{_format_integer(int(applicable['descapitalizado'].eq('Si').sum()))} "
            "descapitalizados."
        ),
        finding=finding,
        slide="2 · Perfil de la población",
        note=(
            f"Universo aplicable: {_format_integer(len(applicable))} registros. Eje vertical "
            "normalizado dentro de cada estado; los tamaños de grupo difieren."
        ),
        figure=fig,
    )


def _capital_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> ExecutiveChart:
    applicable = _applicable_frame(frame)
    applicable["capital_mas_bono"] = pd.to_numeric(
        applicable["capital_mas_bono"], errors="coerce"
    )
    fig, ax = _canvas(
        "El capital más bono difiere entre cuentas descapitalizadas y no descapitalizadas",
        "Percentiles de capital disponible en el universo aplicable · COP",
        "La escala horizontal es logarítmica. P10–P90: línea; P25–P75: intervalo; "
        "P50: mediana; P99: rombo. Se excluyen capitales no positivos solo para esta escala; "
        "los máximos y conteos excluidos se informan en la nota.",
        source_name,
        cutoff,
        generation_max,
    )
    groups = [
        ("No", "No descapitalizado", 0.65),
        ("Si", "Descapitalizado", 0.25),
    ]
    y_positions = []
    outlier_counts: dict[str, int] = {}
    summaries: dict[str, pd.Series] = {}
    nonpositive_counts: dict[str, int] = {}
    for value, label, y in groups:
        values = applicable.loc[
            applicable["descapitalizado"].eq(value), "capital_mas_bono"
        ].dropna()
        positive = values.loc[values > 0]
        quantiles = positive.quantile([0.10, 0.25, 0.50, 0.75, 0.90, 0.99])
        summaries[value] = quantiles
        nonpositive_counts[value] = int((values <= 0).sum())
        iqr = quantiles.loc[0.75] - quantiles.loc[0.25]
        outlier_counts[value] = int((positive > quantiles.loc[0.75] + 1.5 * iqr).sum())
        y_positions.append(y)
        ax.plot(
            [quantiles.loc[0.10] / 1e6, quantiles.loc[0.90] / 1e6],
            [y, y],
            color=LIGHT_GRAY,
            linewidth=10,
            solid_capstyle="round",
            zorder=1,
        )
        ax.plot(
            [quantiles.loc[0.25] / 1e6, quantiles.loc[0.75] / 1e6],
            [y, y],
            color=BLUE if value == "Si" else CYAN,
            linewidth=18,
            solid_capstyle="butt",
            zorder=2,
        )
        ax.scatter(
            quantiles.loc[0.50] / 1e6,
            y,
            s=150,
            color=YELLOW,
            edgecolor=BLUE,
            linewidth=1.5,
            zorder=3,
        )
        ax.scatter(
            quantiles.loc[0.99] / 1e6,
            y,
            s=105,
            marker="D",
            color=BLUE,
            edgecolor=WHITE,
            linewidth=0.8,
            zorder=4,
        )
        ax.text(
            quantiles.loc[0.50] / 1e6,
            y + 0.12,
            f"P50 {_format_millions(float(quantiles.loc[0.50]))}",
            ha="center",
            va="bottom",
            fontsize=12,
            color=BLUE,
            fontfamily=FONT,
        )

    ax.set_yticks(y_positions, [label for _, label, _ in groups])
    ax.set_xscale("log")
    ax.set_xlim(20, max(float(values.max()) for _, _, _ in groups) / 1e6 * 1.18)
    ax.set_xlabel(
        "Capital más bono (millones de COP; escala logarítmica)",
        color=BLUE,
        fontsize=14,
        fontfamily=FONT,
        labelpad=10,
    )
    ax.set_ylim(0, 1.05)
    tick_values = [10, 30, 100, 300, 1_000, 3_000, 10_000]
    ax.set_xticks(tick_values, [f"{_format_integer(tick)}" for tick in tick_values])
    ax.get_xaxis().set_minor_locator(NullLocator())
    _clean_axis(ax, grid_axis="x")
    ax.set_yticklabels([label for _, label, _ in groups], fontsize=14, color=BLUE)
    legend = [
        Line2D([0], [0], color=LIGHT_GRAY, linewidth=8, label="P10–P90"),
        Line2D([0], [0], color=BLUE, linewidth=12, label="P25–P75"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=YELLOW,
               markeredgecolor=BLUE, markersize=10, label="P50"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=BLUE,
               markersize=8, label="P99"),
    ]
    ax.legend(handles=legend, frameon=False, loc="lower right", ncol=4, fontsize=11)
    no_status = summaries["No"]
    yes_status = summaries["Si"]
    yes_tail_ratio = float(yes_status.loc[0.99] / yes_status.loc[0.50])
    no_tail_ratio = float(no_status.loc[0.99] / no_status.loc[0.50])
    finding = (
        f"Entre capitales positivos, mediana: "
        f"{_format_millions(float(yes_status.loc[0.50]), 1)} en descapitalizados "
        f"vs. {_format_millions(float(no_status.loc[0.50]), 1)} en no descapitalizados. "
        f"P99/P50: {_format_decimal(yes_tail_ratio, 1)}x y "
        f"{_format_decimal(no_tail_ratio, 1)}x, respectivamente, mostrando la cola superior. "
        f"Máximo observado en el universo aplicable: "
        f"{_format_millions(float(applicable['capital_mas_bono'].max()))}; "
        f"valores sobre la cerca de Tukey: {_format_integer(sum(outlier_counts.values()))}."
    )
    excluded = sum(nonpositive_counts.values())
    return ExecutiveChart(
        key="03_distribucion_capital",
        title="Distribución del capital disponible",
        objective="Comparar niveles típicos, dispersión y cola superior sin ocultar la asimetría.",
        variables="Capital + Bono; Descapitalizado; Riesgo (aplicabilidad)",
        population=(
            f"Universo aplicable: {_format_integer(len(applicable))}; "
            f"{_format_integer(excluded)} capitales no positivos omitidos del eje logarítmico."
        ),
        finding=finding,
        slide="3 · Capital disponible y dispersión",
        note=(
            f"Universo aplicable: {_format_integer(len(applicable))} registros. No positivos "
            f"excluidos del gráfico: {_format_integer(excluded)} "
            f"(No descapitalizado: {_format_integer(nonpositive_counts['No'])}; "
            f"descapitalizado: {_format_integer(nonpositive_counts['Si'])}). "
            f"Valores sobre cerca de Tukey (descriptivo): No="
            f"{_format_integer(outlier_counts['No'])}, Sí="
            f"{_format_integer(outlier_counts['Si'])}."
        ),
        figure=fig,
    )


def _isc_segments(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    calculated = calculate_isc(frame)
    applicable = calculated["isc_aplicable"] & calculated["ISC"].notna()
    isc = calculated.loc[applicable, "ISC"]
    bins = pd.cut(
        isc,
        [-np.inf, 1.0, 1.2, np.inf],
        right=False,
        labels=["ISC < 1,00", "1,00 ≤ ISC < 1,20", "ISC ≥ 1,20"],
    )
    return calculated, bins, applicable


def _isc_segment_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> ExecutiveChart:
    _, segments, _ = _isc_segments(frame)
    labels = ["ISC < 1,00", "1,00 ≤ ISC < 1,20", "ISC ≥ 1,20"]
    counts = [int(segments.value_counts(sort=False).reindex(labels, fill_value=0).loc[label]) for label in labels]
    total = int(segments.notna().sum())
    shares = [count / max(total, 1) * 100 for count in counts]
    fig, ax = _canvas(
        "El 64,4% del universo calculable tiene ISC menor que 1,00",
        "Segmentación exploratoria en grupos mutuamente excluyentes",
        "ISC = (Capital + Bono) / Capital necesario para financiar un SMMLV. Los intervalos "
        "segmentan, pero no determinan elegibilidad final para la modalidad mutualizada.",
        source_name,
        cutoff,
        generation_max,
    )
    positions = np.arange(len(labels))
    bars = ax.bar(
        positions,
        counts,
        width=0.58,
        color=[BLUE, YELLOW, GRAY],
        edgecolor="none",
    )
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Registros", color=BLUE, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.set_ylim(0, max(counts) * 1.25)
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: _format_integer(value))
    )
    _clean_axis(ax, grid_axis="y")
    for bar, count, share in zip(bars, counts, shares, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(counts) * 0.025,
            f"{_format_integer(count)}\n{_format_decimal(share, 1)}%",
            ha="center",
            va="bottom",
            color=BLUE,
            fontsize=15,
            fontweight="bold",
            fontfamily=FONT,
        )
    return ExecutiveChart(
        key="04_segmentacion_isc",
        title="Segmentación mediante ISC",
        objective="Cuantificar tres rangos exhaustivos y excluyentes del ISC calculable.",
        variables="Capital + Bono; Capital necesario para SMMLV; Riesgo (aplicabilidad)",
        population=(
            f"ISC calculable: {_format_integer(total)} de "
            f"{_format_integer(len(frame))} registros aplicables."
        ),
        finding=(
            f"{_format_integer(counts[0])} con ISC < 1,00; "
            f"{_format_integer(counts[1])} entre 1,00 y <1,20; "
            f"{_format_integer(counts[2])} con ISC ≥1,20."
        ),
        slide="4 · Segmentación exploratoria por ISC",
        note=(
            f"Denominador: {_format_integer(total)} registros aplicables con ISC calculable. "
            "Los porcentajes se calculan sobre ese denominador."
        ),
        figure=fig,
    )


def _capital_scenarios_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> tuple[ExecutiveChart, pd.DataFrame]:
    calculated = calculate_isc(frame)
    scenarios = calculate_eligibility_scenarios(
        calculated, thresholds=DEFAULT_ISC_THRESHOLDS
    )
    fig, ax = _canvas(
        "La suma de capital requerido supera al capital disponible en cada escenario",
        "Agregados de registros candidatos por umbral de ISC · billones de COP",
        "«Capital requerido» es la suma de capital_necesario_sm individual exportado por el "
        "cálculo actuarial externo. No es el pasivo ni el déficit actuarial de la bolsa "
        "mutualizada; no modela flujos, supervivencia, rentabilidad ni mutualización.",
        source_name,
        cutoff,
        generation_max,
    )
    x = np.arange(len(scenarios))
    width = 0.34
    available = scenarios["Capital_mas_bono_total"].to_numpy(dtype=float) / 1e12
    required = scenarios["Capital_SM_requerido"].to_numpy(dtype=float) / 1e12
    first = ax.bar(x - width / 2, available, width, color=BLUE, label="Capital + Bono disponible")
    second = ax.bar(x + width / 2, required, width, color=YELLOW, label="Suma de capital requerido individual")
    ax.set_xticks(
        x,
        [
            f"ISC < {_format_decimal(float(threshold), 2)}\n"
            f"(n={_format_integer(int(count))})"
            for threshold, count in zip(
                scenarios["Umbral_ISC"], scenarios["N_candidatos"], strict=True
            )
        ],
    )
    ax.set_ylabel("Billones de COP", color=BLUE, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.set_ylim(0, max(required) * 1.25)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda value, _: _format_decimal(value, 0))
    )
    ax.legend(frameon=False, loc="upper left", fontsize=12)
    _clean_axis(ax, grid_axis="y")
    for bars in (first, second):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(required) * 0.018,
                _format_billions(bar.get_height()),
                ha="center",
                va="bottom",
                color=BLUE,
                fontsize=11,
                fontweight="bold",
                fontfamily=FONT,
            )
    row = scenarios.iloc[0]
    finding = (
        f"En ISC < 1,00: {_format_billions(float(row['Capital_mas_bono_total']))} billones "
        f"de capital + bono vs. {_format_billions(float(row['Capital_SM_requerido']))} "
        "billones sumados de requerimientos individuales observados."
    )
    chart = ExecutiveChart(
        key="05_capital_disponible_vs_requerido",
        title="Capital disponible frente a suma de capital requerido",
        objective="Comparar agregados observados de capital y requerimiento para cada umbral ISC.",
        variables="Capital + Bono; Capital necesario para 1 SM; ISC",
        population="Cohortes anidadas del universo aplicable con ISC calculable.",
        finding=finding,
        slide="5 · Agregados por escenario y límites de interpretación",
        note=(
            "Cada grupo es la cohorte ISC < umbral; el conteo (n) aparece bajo el umbral. "
            "La suma de requerimientos individuales no representa valoración actuarial del fondo."
        ),
        figure=fig,
    )
    return chart, scenarios


def _candidate_expansion_chart(
    frame: pd.DataFrame,
    source_name: str,
    cutoff: str,
    generation_max: str,
) -> ExecutiveChart:
    _, segments, _ = _isc_segments(frame)
    base_count = int((segments == "ISC < 1,00").sum())
    additional_count = int((segments == "1,00 ≤ ISC < 1,20").sum())
    total = base_count + additional_count
    growth = additional_count / max(base_count, 1) * 100
    fig, ax = _canvas(
        "Ampliar el umbral a ISC < 1,20 suma 2.931 registros",
        "Separación entre descapitalización observada y candidatos adicionales del rango",
        "El segmento adicional tiene ISC entre 1,00 y <1,20: su capital + bono alcanza el "
        "requerimiento individual observado, con menor holgura relativa según este cociente. "
        "No equivale a elegibilidad aprobada.",
        source_name,
        cutoff,
        generation_max,
    )
    ax.barh([0], [base_count], height=0.48, color=BLUE, label="ISC < 1,00")
    ax.barh(
        [0],
        [additional_count],
        left=[base_count],
        height=0.48,
        color=YELLOW,
        label="Adicionales: 1,00 ≤ ISC < 1,20",
    )
    ax.text(
        base_count / 2,
        0,
        _format_integer(base_count),
        ha="center",
        va="center",
        color=WHITE,
        fontsize=17,
        fontweight="bold",
        fontfamily=FONT,
    )
    ax.text(
        base_count + additional_count / 2,
        0,
        f"+{_format_integer(additional_count)}",
        ha="center",
        va="center",
        color=BLUE,
        fontsize=15,
        fontweight="bold",
        fontfamily=FONT,
    )
    ax.text(
        total,
        0.40,
        f"Total con ISC < 1,20: {_format_integer(total)}  ·  "
        f"ampliación de {_format_decimal(growth, 1)}%",
        ha="right",
        va="bottom",
        color=BLUE,
        fontsize=14,
        fontweight="bold",
        fontfamily=FONT,
    )
    ax.set_xlim(0, total * 1.08)
    ax.set_ylim(-0.65, 0.9)
    ax.set_yticks([])
    ax.set_xlabel("Registros candidatos", color=BLUE, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, _: _format_integer(value))
    )
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=2, fontsize=12)
    _clean_axis(ax, grid_axis="x")
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    return ExecutiveChart(
        key="06_ampliacion_poblacion_candidata",
        title="Ampliación de la población candidata",
        objective="Mostrar qué registros se agregan al pasar de ISC <1,00 a ISC <1,20.",
        variables="ISC; Descapitalizado observado; Capital + Bono; Capital necesario para 1 SM",
        population=f"{_format_integer(int(segments.notna().sum()))} registros aplicables con ISC calculable.",
        finding=(
            f"Se incorporan {_format_integer(additional_count)} registros con ISC en "
            f"[1,00;1,20), un aumento de {_format_decimal(growth, 1)}% sobre los "
            f"{_format_integer(base_count)} registros con ISC <1,00."
        ),
        slide="6 · Efecto incremental del umbral",
        note=(
            f"Universo: {_format_integer(int(segments.notna().sum()))} registros con ISC "
            "calculable. Grupo adicional segmentado por ISC; no representa elegibilidad final."
        ),
        figure=fig,
    )


def build_executive_charts(
    frame: pd.DataFrame,
    source_name: str = "Base_Proyecto.xlsx",
    cutoff: str = "31/08/2026",
) -> tuple[list[ExecutiveChart], pd.DataFrame, str]:
    """Build the six PowerPoint-ready figures and return scenario data and date note."""
    generation_max, date_note, _, _ = _base_metadata(frame, source_name, cutoff)
    charts = [
        _composition_chart(frame, source_name, cutoff, generation_max),
        _age_chart(frame, source_name, cutoff, generation_max),
        _capital_chart(frame, source_name, cutoff, generation_max),
        _isc_segment_chart(frame, source_name, cutoff, generation_max),
    ]
    scenario_chart, scenarios = _capital_scenarios_chart(
        frame, source_name, cutoff, generation_max
    )
    charts.extend(
        [
            scenario_chart,
            _candidate_expansion_chart(frame, source_name, cutoff, generation_max),
        ]
    )
    return charts, scenarios, date_note


def _summary_frame(charts: list[ExecutiveChart]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Nombre de la gráfica": chart.title,
                "Objetivo": chart.objective,
                "Variables utilizadas": chart.variables,
                "Población o filtro aplicado": chart.population,
                "Principal hallazgo descriptivo": chart.finding,
                "Diapositiva recomendada": chart.slide,
            }
            for chart in charts
        ]
    )


def _summary_markdown(summary: pd.DataFrame, date_note: str) -> str:
    lines = [
        "# Guion de visualizaciones ejecutivas",
        "",
        "> Los conteos son descriptivos y no definen por sí solos elegibilidad.",
        "",
        f"**Validación de fechas:** {date_note}",
        "",
    ]
    for index, row in summary.iterrows():
        lines.extend(
            [
                f"## {index + 1}. {row['Nombre de la gráfica']}",
                "",
                f"- **Objetivo:** {row['Objetivo']}",
                f"- **Variables:** {row['Variables utilizadas']}",
                f"- **Población/filtro:** {row['Población o filtro aplicado']}",
                f"- **Hallazgo:** {row['Principal hallazgo descriptivo']}",
                f"- **Diapositiva sugerida:** {row['Diapositiva recomendada']}",
                "",
            ]
        )
    return "\n".join(lines)


def _executive_html(
    charts: list[ExecutiveChart],
    summary: pd.DataFrame,
    date_note: str,
    source_name: str,
    cutoff: str,
    svg_data: dict[str, str],
) -> str:
    rows = []
    for chart in charts:
        svg = svg_data[chart.key]
        rows.append(
            f"""
<article class="slide">
  <h2>{html.escape(chart.title)}</h2>
  <img alt="{html.escape(chart.title)}" src="data:image/svg+xml;base64,{svg}">
  <p class="finding">{html.escape(chart.finding)}</p>
  <p class="note">{html.escape(chart.note)}</p>
</article>"""
        )
    table_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in summary.itertuples(index=False, name=None)
    )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visualizaciones ejecutivas · Pensión mutualizada</title>
<style>
:root{{--blue:{BLUE};--yellow:{YELLOW};--gray:{GRAY};--light:{PALE_BLUE};--font:"{FONT}",Arial,sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;background:#f4f6f9;color:var(--blue);font-family:var(--font)}}
header,main{{max-width:1280px;margin:auto}} header{{padding:38px 28px 20px}}
h1{{font-size:32px;margin:0 0 10px}} header p{{font-size:15px;line-height:1.55;color:var(--gray)}}
main{{padding:0 20px 48px}} .caveat{{background:#fff5cc;border-left:5px solid var(--yellow);padding:16px 18px;margin:0 0 22px;line-height:1.5}}
.slide{{background:white;padding:22px 22px 18px;margin:18px 0;border-radius:4px;page-break-inside:avoid}}
.slide h2{{font-size:21px;margin:0 0 8px}} .slide img{{display:block;width:100%;height:auto}}
.finding{{font-weight:700;font-size:16px;line-height:1.45;margin:4px 0 8px}}
.note{{font-size:13px;line-height:1.5;color:var(--gray);margin:0}}
.table-wrap{{overflow-x:auto;background:white;padding:16px;margin-top:24px}}
table{{border-collapse:collapse;width:100%;min-width:1000px;font-size:13px;line-height:1.4}}
th,td{{border-bottom:1px solid #d9dee7;text-align:left;vertical-align:top;padding:10px}}
th{{color:var(--blue);background:#eef3fa}}
@media print{{body{{background:white}}header,main{{max-width:none}}.slide,.table-wrap{{box-shadow:none;border:1px solid #ddd}}}}
</style></head>
<body><header><h1>Evaluación de pensión mutualizada · Visualizaciones ejecutivas</h1>
<p>Material preparado para discusión con el equipo de Protección. Fuente: {html.escape(source_name)} · Corte informado: {html.escape(cutoff)}.</p></header>
<main><aside class="caveat"><strong>Validación de fecha:</strong> {html.escape(date_note)}
<br>El análisis ISC es segmentación exploratoria; los escenarios no representan elegibilidad final ni valoración actuarial de una bolsa mutualizada.
El capital requerido agregado suma cálculos individuales externos observados en el Excel.</aside>
{"".join(rows)}
<section class="table-wrap"><h2>Resumen para presentación</h2><table><thead><tr>
{"".join(f"<th>{html.escape(str(column))}</th>" for column in summary.columns)}
</tr></thead><tbody>{table_rows}</tbody></table></section>
</main></body></html>"""


def generate_executive_package(
    frame: pd.DataFrame,
    reports_dir: str | Path,
    source_name: str = "Base_Proyecto.xlsx",
    cutoff: str = "31/08/2026",
) -> dict[str, Path]:
    """Export six 16:9 PNG/SVG figures, summary tables, and a separate HTML report."""
    output = Path(reports_dir)
    figure_dir = output / "outputs" / "presentacion_ejecutiva" / "figures"
    table_dir = output / "tables"
    figure_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)

    charts, _, date_note = build_executive_charts(frame, source_name, cutoff)
    svg_data: dict[str, str] = {}
    for chart in charts:
        png_path = figure_dir / f"{chart.key}.png"
        svg_path = figure_dir / f"{chart.key}.svg"
        chart.figure.savefig(
            png_path,
            format="png",
            dpi=DPI,
            facecolor=WHITE,
            bbox_inches=None,
        )
        chart.figure.savefig(
            svg_path,
            format="svg",
            facecolor=WHITE,
            bbox_inches=None,
        )
        svg_data[chart.key] = base64.b64encode(svg_path.read_bytes()).decode("ascii")

    summary = _summary_frame(charts)
    csv_path = table_dir / "resumen_graficas_ejecutivas.csv"
    markdown_path = table_dir / "resumen_graficas_ejecutivas.md"
    html_path = output / "exploracion_ejecutiva.html"
    summary.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")
    markdown_path.write_text(_summary_markdown(summary, date_note), encoding="utf-8")
    html_path.write_text(
        _executive_html(charts, summary, date_note, source_name, cutoff, svg_data),
        encoding="utf-8",
    )
    for chart in charts:
        plt.close(chart.figure)
    return {
        "html": html_path,
        "summary_csv": csv_path,
        "summary_markdown": markdown_path,
        "figures_dir": figure_dir,
    }


if __name__ == "__main__":
    workbook = find_workbook()
    report_paths = generate_executive_package(
        load_workbook(workbook),
        workbook.parent / "reports",
        source_name=workbook.name,
    )
    for output_path in report_paths.values():
        print(output_path)
