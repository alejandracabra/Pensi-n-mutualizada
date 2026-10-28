"""Gráficos EDA interactivos construidos sobre datos agregados."""

from __future__ import annotations

from collections.abc import Iterable
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from src.data.profile import safe_category_counts
from src.visualization.palette import (
    PLOTLY_TEMPLATE,
    PROTECCION_ACCENT,
    PROTECCION_CATEGORICAL,
    PROTECCION_DARK,
    PROTECCION_LIGHT,
    PROTECCION_PRIMARY,
    PROTECCION_SECONDARY,
)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _histogram(frame: pd.DataFrame, column: str, bins: int = 40) -> pd.DataFrame:
    """Agrupa observaciones en intervalos para no exportar datos individuales."""
    values = _numeric(frame, column)
    if len(values) < 10:
        return pd.DataFrame(columns=["intervalo", "conteo", "centro", "inicio", "fin"])
    if values.nunique() == 1:
        label = "Valor constante"
        value = float(values.iloc[0])
        return pd.DataFrame(
            {
                "intervalo": [label],
                "conteo": [len(values)],
                "centro": [value],
                "inicio": [value],
                "fin": [value],
            }
        )
    lower, upper = values.quantile([0.01, 0.99]).to_numpy()
    if lower >= upper:
        lower, upper = values.min(), values.max()
    inner_bins = min(bins, max(5, len(values) // 10))
    core_values = values[(values >= lower) & (values <= upper)]
    inner_counts, edges = np.histogram(
        core_values.to_numpy(), bins=inner_bins, range=(lower, upper)
    )
    grouped_counts: list[int] = []
    grouped_edges: list[tuple[float, float]] = []
    pending_count = 0
    pending_start = float(edges[0])
    for index, count in enumerate(inner_counts):
        pending_count += int(count)
        if pending_count >= 10:
            grouped_counts.append(pending_count)
            grouped_edges.append((pending_start, float(edges[index + 1])))
            pending_start = float(edges[index + 1])
            pending_count = 0
    if pending_count:
        if grouped_counts:
            grouped_counts[-1] += pending_count
            grouped_edges[-1] = (grouped_edges[-1][0], float(edges[-1]))
        else:
            grouped_counts.append(pending_count)
            grouped_edges.append((float(edges[0]), float(edges[-1])))

    left_tail = int((values < lower).sum())
    right_tail = int((values > upper).sum())
    if left_tail >= 10:
        grouped_counts.insert(0, left_tail)
        grouped_edges.insert(0, (float(lower), float(lower)))
    elif left_tail and grouped_counts:
        grouped_counts[0] += left_tail
    if right_tail >= 10:
        grouped_counts.append(right_tail)
        grouped_edges.append((float(upper), float(upper)))
    elif right_tail and grouped_counts:
        grouped_counts[-1] += right_tail

    labels = []
    centers = []
    starts = []
    ends = []
    for index, ((start, end), count) in enumerate(zip(grouped_edges, grouped_counts, strict=True)):
        if left_tail >= 10 and index == 0:
            label = "≤ percentil 1"
            center = float(lower)
        elif right_tail >= 10 and index == len(grouped_edges) - 1:
            label = "≥ percentil 99"
            center = float(upper)
        else:
            label = f"{start:,.2f} – {end:,.2f}"
            center = (start + end) / 2
        labels.append(label)
        centers.append(center)
        starts.append(start)
        ends.append(end)
    return pd.DataFrame(
        {
            "intervalo": labels,
            "conteo": grouped_counts,
            "centro": centers,
            "inicio": starts,
            "fin": ends,
        }
    )


def _density_curve(histogram: pd.DataFrame) -> pd.DataFrame:
    """Estima una densidad suavizada usando únicamente conteos por intervalo."""
    if histogram.empty:
        return pd.DataFrame(columns=["x", "densidad"])
    counts = histogram["conteo"].to_numpy(dtype=float)
    centers = histogram["centro"].to_numpy(dtype=float)
    widths = (histogram["fin"] - histogram["inicio"]).to_numpy(dtype=float)
    positive_widths = widths[widths > 0]
    fallback_width = float(np.median(positive_widths)) if positive_widths.size else 1.0
    widths = np.where(widths > 0, widths, fallback_width)
    density = counts / max(counts.sum(), 1) / widths
    if len(counts) < 3 or counts.sum() == 0:
        return pd.DataFrame({"x": centers, "densidad": density})
    smooth = np.convolve(density, np.array([0.25, 0.5, 0.25]), mode="same")
    return pd.DataFrame({"x": centers, "densidad": smooth})


def distribution_figures(
    frame: pd.DataFrame,
    column: str,
    label: str | None = None,
    logarithmic: bool = False,
) -> dict[str, go.Figure]:
    """Genera histograma, densidad y resumen boxplot sin publicar microdatos."""
    if column not in frame.columns:
        return {}
    display = label or column.replace("_", " ").capitalize()
    values = _numeric(frame, column)
    if values.empty:
        return {}
    histogram = _histogram(frame, column)
    color = PROTECCION_PRIMARY
    figures: dict[str, go.Figure] = {}

    hist = px.bar(
        histogram,
        x="intervalo",
        y="conteo",
        color_discrete_sequence=[color],
        labels={"intervalo": display, "conteo": "Registros"},
        title=f"Distribución de {display}",
    )
    hist.update_traces(
        hovertemplate="Intervalo: %{x}<br>Registros: %{y:,}<extra></extra>"
    )
    hist.update_layout(template=PLOTLY_TEMPLATE, showlegend=False, xaxis_tickangle=-35)
    if logarithmic and (histogram["centro"] > 0).all():
        hist.update_xaxes(type="log")
    figures["histograma"] = hist

    positive = values[values > 0]
    if logarithmic and len(positive) > 1 and positive.nunique() > 1:
        positive_frame = pd.DataFrame({column: positive})
        log_histogram = _histogram(positive_frame, column)
        log_fig = px.bar(
            log_histogram,
            x="centro",
            y="conteo",
            color_discrete_sequence=[PROTECCION_DARK],
            labels={"centro": display, "conteo": "Registros"},
            title=f"Distribución de {display} en escala logarítmica (valores positivos)",
        )
        log_fig.update_traces(
            hovertemplate="Centro del intervalo: %{x:,.2f}<br>Registros: %{y:,}<extra></extra>"
        )
        log_fig.update_xaxes(type="log")
        log_fig.update_layout(template=PLOTLY_TEMPLATE, showlegend=False)
        figures["histograma_log"] = log_fig

    density = _density_curve(histogram)
    density_fig = go.Figure()
    density_fig.add_trace(
        go.Scatter(
            x=density["x"],
            y=density["densidad"],
            mode="lines",
            fill="tozeroy",
            line={"color": PROTECCION_SECONDARY, "width": 2},
            fillcolor="rgba(0,168,89,0.18)",
            hovertemplate=f"{display}: %{{x:,.2f}}<br>Densidad relativa: %{{y:.4f}}<extra></extra>",
        )
    )
    density_fig.update_layout(
        title=f"Densidad aproximada de {display} (a partir de intervalos agregados)",
        xaxis_title=display,
        yaxis_title="Densidad relativa",
        template=PLOTLY_TEMPLATE,
    )
    figures["densidad"] = density_fig

    quartiles = values.quantile([0.25, 0.5, 0.75])
    iqr = quartiles.loc[0.75] - quartiles.loc[0.25]
    low = float(values[values >= quartiles.loc[0.25] - 1.5 * iqr].min())
    high = float(values[values <= quartiles.loc[0.75] + 1.5 * iqr].max())
    box = go.Figure(
        go.Box(
            x=[display],
            q1=[float(quartiles.loc[0.25])],
            median=[float(quartiles.loc[0.5])],
            q3=[float(quartiles.loc[0.75])],
            lowerfence=[low],
            upperfence=[high],
            boxpoints=False,
            marker_color=color,
            name=display,
            hovertemplate=(
                f"{display}<br>Q1: {quartiles.loc[0.25]:,.2f}"
                f"<br>Mediana: {quartiles.loc[0.5]:,.2f}"
                f"<br>Q3: {quartiles.loc[0.75]:,.2f}<extra></extra>"
            ),
        )
    )
    box.update_layout(title=f"Resumen boxplot de {display}", template=PLOTLY_TEMPLATE, showlegend=False)
    figures["boxplot"] = box
    return figures


def completeness_figures(frame: pd.DataFrame) -> dict[str, go.Figure]:
    """Genera completitud por variable y co-ocurrencia agregada de nulos."""
    missing = frame.isna().mean().mul(100).sort_values(ascending=True)
    bar = go.Figure(
        go.Bar(
            x=missing.values,
            y=missing.index,
            orientation="h",
            marker_color=[PROTECCION_PRIMARY if value == 0 else PROTECCION_SECONDARY for value in missing.values],
            customdata=frame.isna().sum().reindex(missing.index).to_numpy(),
            hovertemplate="%{y}<br>Nulos: %{customdata:,}<br>Porcentaje: %{x:.2f}%<extra></extra>",
        )
    )
    bar.update_layout(
        title="Porcentaje de valores faltantes por variable",
        xaxis_title="Porcentaje de nulos",
        yaxis_title="",
        template=PLOTLY_TEMPLATE,
    )

    missing_mask = frame.isna().astype(np.uint8)
    co_missing_count = missing_mask.T @ missing_mask
    co_missing_pct = co_missing_count.div(max(len(frame), 1)).mul(100)
    display_count = co_missing_count.astype(float).to_numpy(copy=True)
    display_count[display_count < 10] = np.nan
    matrix = go.Figure(
        go.Heatmap(
            z=co_missing_pct.to_numpy(),
            x=frame.columns.tolist(),
            y=frame.columns.tolist(),
            customdata=display_count,
            colorscale=[[0, PROTECCION_LIGHT], [1, PROTECCION_DARK]],
            colorbar={"title": "% de registros"},
            hovertemplate=(
                "Variables: %{y} / %{x}<br>"
                "Porcentaje con ambas nulas: %{z:.2f}%<br>"
                "Conteo: %{customdata:.0f}<extra></extra>"
            ),
        )
    )
    matrix.update_layout(
        title="Matriz agregada de co-ocurrencia de valores nulos (celdas con conteo < 10 suprimidas)",
        xaxis_title="Variable",
        yaxis_title="",
        template=PLOTLY_TEMPLATE,
    )
    return {"completitud": bar, "matriz_nulos": matrix}


def categorical_figures(frame: pd.DataFrame, column: str, label: str | None = None) -> dict[str, go.Figure]:
    """Genera barras de participación y distribuciones de riesgo agregadas."""
    if column not in frame.columns:
        return {}
    summary = safe_category_counts(frame, column)
    if len(summary) > 30:
        largest = summary.nlargest(29, "registros")
        others = summary.loc[~summary.index.isin(largest.index), "registros"].sum()
        summary = pd.concat(
            [
                largest,
                pd.DataFrame(
                    {
                        "categoria": ["Otros"],
                        "registros": [others],
                        "participacion_pct": [others / max(len(frame), 1) * 100],
                    }
                ),
            ],
            ignore_index=True,
        )
    display = label or column.replace("_", " ").capitalize()
    colors = list(PROTECCION_CATEGORICAL)
    bar = px.bar(
        summary,
        x="categoria",
        y="registros",
        color="categoria",
        color_discrete_sequence=colors,
        custom_data=["participacion_pct"],
        title=f"Registros por {display}",
        labels={"categoria": display, "registros": "Registros"},
    )
    bar.update_traces(hovertemplate="%{x}<br>Registros: %{y:,}<br>Participación: %{customdata[0]:.2f}%<extra></extra>")
    bar.update_layout(template=PLOTLY_TEMPLATE, showlegend=False)

    pie = px.sunburst(
        summary,
        path=["categoria"],
        values="registros",
        color="categoria",
        color_discrete_sequence=colors,
        title=f"Participación por {display}",
    )
    pie.update_traces(hovertemplate="%{label}<br>Registros: %{value:,}<br>Participación: %{percentRoot:.2%}<extra></extra>")
    pie.update_layout(template=PLOTLY_TEMPLATE)
    return {"barras": bar, "sunburst": pie}


def risk_hierarchy_figures(frame: pd.DataFrame) -> dict[str, go.Figure]:
    """Compara Riesgo y Riesgo 3 en un treemap y un sunburst agregados."""
    dimensions = [column for column in ("riesgo", "riesgo_3") if column in frame.columns]
    if len(dimensions) != 2:
        return {}
    grouped = (
        frame.groupby(dimensions, dropna=False, observed=True)
        .size()
        .rename("registros")
        .reset_index()
    )
    grouped[dimensions] = grouped[dimensions].fillna("Sin dato")
    small = grouped["registros"] < 10
    grouped.loc[small, dimensions] = "Otros / grupos pequeños"
    grouped = grouped.groupby(dimensions, observed=True)["registros"].sum().reset_index()
    figures = {}
    for name, constructor in (("sunburst_riesgos", px.sunburst), ("treemap_riesgos", px.treemap)):
        fig = constructor(
            grouped,
            path=dimensions,
            values="registros",
            color=dimensions[0],
            color_discrete_sequence=PROTECCION_CATEGORICAL,
            title="Composición conjunta de Riesgo y Riesgo 3",
        )
        fig.update_layout(template=PLOTLY_TEMPLATE)
        figures[name] = fig
    return figures


def coverage_band(frame: pd.DataFrame) -> pd.Series:
    """Calcula cobertura y clasificación; valores no finitos se conservan como faltantes."""
    capital = pd.to_numeric(frame.get("capital"), errors="coerce")
    required = pd.to_numeric(frame.get("capital_necesario_sm"), errors="coerce")
    coverage = capital.div(required.where(required > 0))
    bands = pd.cut(
        coverage,
        bins=[-np.inf, 0.5, 0.8, 1.0, np.inf],
        labels=["< 0.5", "0.5 a < 0.8", "0.8 a < 1", ">= 1"],
        right=False,
        include_lowest=True,
    )
    return bands.astype("string").fillna("No calculable")


def coverage_figure(frame: pd.DataFrame) -> go.Figure:
    """Visualiza cobertura sobre capital requerido en categorías agregadas."""
    counts = coverage_band(frame).value_counts().reindex(
        ["< 0.5", "0.5 a < 0.8", "0.8 a < 1", ">= 1", "No calculable"], fill_value=0
    )
    suppressed = counts < 10
    labels = [
        f"{value} (n < 10)" if is_suppressed else value
        for value, is_suppressed in zip(counts.index, suppressed, strict=True)
    ]
    visible_counts = counts.astype(float).where(~suppressed, np.nan)
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=visible_counts.values,
            marker_color=[PROTECCION_DARK, PROTECCION_SECONDARY, "#45B8AC", PROTECCION_PRIMARY, "#9AA9A3"],
            text=[
                "" if is_suppressed else f"{value / max(counts.sum(), 1):.1%}"
                for value, is_suppressed in zip(counts.values, suppressed, strict=True)
            ],
            textposition="outside",
            hovertemplate="Cobertura: %{x}<br>Registros: %{y:,}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Clasificación experimental: capital / capital necesario para 1 SM",
        xaxis_title="Banda de cobertura",
        yaxis_title="Registros",
        template=PLOTLY_TEMPLATE,
        showlegend=False,
    )
    return fig


def binned_relationship(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    title: str,
    bins: int = 35,
    logarithmic_x: bool = False,
    logarithmic_y: bool = False,
) -> go.Figure | None:
    """Traza una matriz de conteos 2D; ninguna coordenada individual se exporta."""
    if x_column not in frame.columns or y_column not in frame.columns:
        return None
    subset = frame[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if logarithmic_x:
        subset = subset[subset[x_column] > 0]
        subset[x_column] = np.log10(subset[x_column])
    if logarithmic_y:
        subset = subset[subset[y_column] > 0]
        subset[y_column] = np.log10(subset[y_column])
    if len(subset) < 2:
        return None
    heatmap, x_edges, y_edges = np.histogram2d(
        subset[x_column].to_numpy(),
        subset[y_column].to_numpy(),
        bins=min(bins, max(5, int(np.sqrt(len(subset)) / 3))),
    )
    x_labels = (x_edges[:-1] + x_edges[1:]) / 2
    y_labels = (y_edges[:-1] + y_edges[1:]) / 2
    if logarithmic_x:
        x_labels = np.power(10, x_labels)
    if logarithmic_y:
        y_labels = np.power(10, y_labels)
    fig = go.Figure(
        go.Heatmap(
            x=x_labels,
            y=y_labels,
            z=np.where(heatmap.T < 10, np.nan, heatmap.T),
            colorscale=[[0, PROTECCION_LIGHT], [0.55, PROTECCION_ACCENT], [1, PROTECCION_DARK]],
            colorbar={"title": "Registros"},
            hovertemplate=f"{x_column}: %{{x:,.2f}}<br>{y_column}: %{{y:,.2f}}<br>Registros: %{{z:.0f}}<extra></extra>",
        )
    )
    fig.update_layout(title=title, xaxis_title=x_column, yaxis_title=y_column, template=PLOTLY_TEMPLATE)
    if logarithmic_x:
        fig.update_xaxes(type="log")
    if logarithmic_y:
        fig.update_yaxes(type="log")
    return fig


def scatter_matrix_figure(frame: pd.DataFrame, columns: Iterable[str]) -> go.Figure | None:
    """Construye una matriz de heatmaps bivariados sobre conteos por celdas."""
    selected = [column for column in columns if column in frame.columns]
    if len(selected) < 2:
        return None
    selected = selected[:4]
    size = len(selected)
    fig = make_subplots(
        rows=size,
        cols=size,
        shared_xaxes=False,
        shared_yaxes=False,
        horizontal_spacing=0.04,
        vertical_spacing=0.06,
        subplot_titles=[f"{y} vs {x}" for y in selected for x in selected],
    )
    for row, y_column in enumerate(selected, start=1):
        for col, x_column in enumerate(selected, start=1):
            subset = frame[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
            if x_column == y_column:
                hist = _histogram(frame, x_column, bins=20)
                fig.add_trace(
                    go.Bar(x=hist["centro"], y=hist["conteo"], marker_color=PROTECCION_PRIMARY),
                    row=row,
                    col=col,
                )
            elif not subset.empty:
                z, x_edges, y_edges = np.histogram2d(
                    subset[x_column], subset[y_column], bins=18
                )
                fig.add_trace(
                    go.Heatmap(
                        x=(x_edges[:-1] + x_edges[1:]) / 2,
                        y=(y_edges[:-1] + y_edges[1:]) / 2,
                        z=np.where(z.T < 10, np.nan, z.T),
                        colorscale=[[0, PROTECCION_LIGHT], [1, PROTECCION_DARK]],
                        showscale=False,
                        hovertemplate="Registros: %{z:.0f}<extra></extra>",
                    ),
                    row=row,
                    col=col,
                )
            fig.update_xaxes(title_text=x_column if row == size else "", row=row, col=col)
            fig.update_yaxes(title_text=y_column if col == 1 else "", row=row, col=col)
    fig.update_layout(
        title="Matriz de relaciones bivariadas (conteos agregados)",
        template=PLOTLY_TEMPLATE,
        height=240 * size,
        showlegend=False,
    )
    return fig


def financial_correlation_figure(frame: pd.DataFrame, columns: Iterable[str]) -> go.Figure | None:
    """Muestra correlaciones de Pearson de variables financieras."""
    selected = [column for column in columns if column in frame.columns]
    if len(selected) < 2:
        return None
    corr = frame[selected].apply(pd.to_numeric, errors="coerce").corr(method="pearson")
    fig = go.Figure(
        go.Heatmap(
            z=corr.to_numpy(),
            x=corr.columns,
            y=corr.index,
            zmin=-1,
            zmax=1,
            colorscale=[[0, PROTECCION_DARK], [0.5, "#FFFFFF"], [1, PROTECCION_PRIMARY]],
            text=np.round(corr.to_numpy(), 2),
            texttemplate="%{text}",
            hovertemplate="%{y} / %{x}<br>Correlación: %{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(title="Matriz de correlación de Pearson", template=PLOTLY_TEMPLATE)
    return fig


def financial_violin_figures(frame: pd.DataFrame, columns: Iterable[str]) -> dict[str, go.Figure]:
    """Representa violines de densidad derivados de intervalos, no de microdatos."""
    figures = {}
    for column in columns:
        if column not in frame:
            continue
        hist = _histogram(frame, column)
        density = _density_curve(hist)
        if density.empty:
            continue
        widths = density["densidad"].to_numpy()
        maximum = widths.max() if widths.max() else 1.0
        widths = widths / maximum * 0.42
        x = density["x"].to_numpy()
        fig = go.Figure(
            go.Scatter(
                x=np.concatenate([-widths, widths[::-1]]),
                y=np.concatenate([x, x[::-1]]),
                fill="toself",
                fillcolor="rgba(0,168,89,0.28)",
                line={"color": PROTECCION_SECONDARY},
                text=np.concatenate([density["densidad"], density["densidad"][::-1]]),
                hovertemplate=f"{column}: %{{y:,.2f}}<br>Densidad agregada: %{{text:.4f}}<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Violín aproximado de {column} (densidad agregada)",
            xaxis_title="Densidad relativa",
            yaxis_title=column,
            xaxis={"visible": False, "range": [-0.5, 0.5]},
            template=PLOTLY_TEMPLATE,
            showlegend=False,
        )
        figures[f"violin_{column}"] = fig
    return figures
