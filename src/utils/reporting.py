"""Construcción de KPIs y reportes reproducibles en Markdown y HTML."""

from __future__ import annotations

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
    PROTECCION_DARK,
    PROTECCION_LIGHT,
    PROTECCION_PRIMARY,
    PROTECCION_SECONDARY,
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
            "capital inferior al capital necesario para 1 SM."
        )
    findings.append(
        "La cobertura es un indicador exploratorio de suficiencia de capital individual; "
        "no incorpora supervivencia, rentabilidad, gastos, reglas de beneficio ni "
        "redistribución colectiva y no constituye una medida de solvencia."
    )
    return findings


def build_markdown_report(frame: pd.DataFrame, source_name: str) -> str:
    """Genera un informe técnico con tablas, KPIs y hallazgos automáticos."""
    overview = overview_table(frame)
    numeric = numeric_columns(frame)
    kpis = calculate_kpis(frame)
    demo = numeric_summary(frame, DEMOGRAPHIC_COLUMNS)
    financial = numeric_summary(frame, FINANCIAL_COLUMNS)
    outliers = iqr_outlier_summary(frame, [*DEMOGRAPHIC_COLUMNS, *FINANCIAL_COLUMNS])
    findings = automatic_findings(frame, kpis)

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

Las variables monetarias conservan las unidades de la fuente; valide moneda y fecha de valoración con el responsable del dato.

{_table_markdown(financial)}

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
  <p class="note">La vista de participación responde a los filtros. Los demás gráficos resumen la población completa.</p>
</section>
<script id="aggregate-data" type="application/json">{records}</script>
<script>
(() => {{
  const rows = JSON.parse(document.getElementById("aggregate-data").textContent);
  const risk = document.getElementById("filter-risk");
  const sex = document.getElementById("filter-sex");
  const result = document.getElementById("filter-result");
  const addOptions = (select, values) => [...new Set(values)].sort().forEach(value => {{
    const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option);
  }});
  addOptions(risk, rows.map(row => row.riesgo)); addOptions(sex, rows.map(row => row.sexo));
  const update = () => {{
    const selected = rows.filter(row => (!risk.value || row.riesgo === risk.value) && (!sex.value || row.sexo === sex.value));
    const count = selected.reduce((total, row) => total + row.registros, 0);
    result.textContent = `Registros en el filtro: ${{count.toLocaleString("es-CO")}}`;
    const dimension = risk.value ? "sexo" : "riesgo";
    const grouped = selected.reduce((totals, row) => {{
      totals[row[dimension]] = (totals[row[dimension]] || 0) + row.registros;
      return totals;
    }}, {{}});
    Plotly.react("filter-chart", [{{
      type: "bar",
      x: Object.keys(grouped),
      y: Object.values(grouped),
      marker: {{color: "{PROTECCION_PRIMARY}"}},
      hovertemplate: "%{{x}}<br>Registros: %{{y:,}}<extra></extra>"
    }}], {{
      title: risk.value ? "Registros por sexo" : "Registros por riesgo",
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{color: "{PROTECCION_DARK}"}},
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
) -> str:
    """Genera un dashboard HTML autónomo con Plotly embebido y datos agregados."""
    kpis = calculate_kpis(frame)
    sections = []
    for index, (name, figure) in enumerate(figures.items()):
        div_id = f"eda-figure-{index}"
        chart = pio.to_html(
            figure,
            full_html=False,
            include_plotlyjs=False,
            div_id=div_id,
            config={"responsive": True, "displaylogo": False},
        )
        sections.append(
            f'<section class="chart"><h2>{html.escape(name.replace("_", " ").capitalize())}</h2>{chart}</section>'
        )
    filter_panel = _dashboard_filter(frame)
    findings = "".join(
        f"<li>{html.escape(text)}</li>" for text in automatic_findings(frame, kpis)
    )
    styles = f"""
    :root {{ --primary:{PROTECCION_PRIMARY}; --secondary:{PROTECCION_SECONDARY};
      --light:{PROTECCION_LIGHT}; --dark:{PROTECCION_DARK}; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:#23342e; background:#f4f8f6; font-family:Arial,sans-serif; }}
    header {{ padding:3rem max(1.5rem,calc((100vw - 1200px)/2)); color:white;
      background:linear-gradient(120deg,var(--dark),var(--secondary)); }}
    header h1 {{ margin:.2rem 0 1rem; max-width:900px; font-size:clamp(2rem,4vw,3rem); }}
    header p {{ max-width:850px; line-height:1.6; }}
    main {{ max-width:1200px; margin:2rem auto; padding:0 1rem; }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; }}
    .kpi,.chart,.filter-panel,.summary {{ background:white; border-radius:12px; padding:1.2rem;
      box-shadow:0 2px 12px #173f3510; }}
    .kpi span {{ display:block; color:#52645d; font-size:.9rem; }}
    .kpi strong {{ display:block; margin-top:.5rem; color:var(--dark); font-size:1.4rem; }}
    .chart,.filter-panel,.summary {{ margin-top:1.25rem; }}
    .chart h2 {{ color:var(--dark); font-size:1.15rem; }}
    select {{ display:block; margin:.4rem 0 1rem; padding:.55rem; min-width:220px; }}
    .note {{ color:#52645d; font-size:.9rem; }}
    footer {{ padding:2rem 1rem; text-align:center; color:#52645d; }}
    """
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Análisis exploratorio agregado de la base del proyecto de pensión mutualizada">
<title>{html.escape(title)}</title><style>{styles}</style><script>{get_plotlyjs()}</script></head><body>
<header><p>Protección · Investigación actuarial y estadística</p><h1>{html.escape(title)}</h1>
<p>Perfilamiento descriptivo inicial de afiliados y saldos. Los hallazgos no constituyen una evaluación de solvencia ni una recomendación de producto.</p></header>
<main><section><h2>Resumen ejecutivo</h2><p>Exploración de {kpis["registros"]:,} registros y {kpis["variables"]} variables. Los gráficos se construyen sobre agregados y estadísticas resumidas; no se incluyen observaciones individuales.</p>
<div class="kpis">{_kpi_cards(kpis)}</div></section>
{filter_panel}
<section class="summary"><h2>Conclusiones automáticas</h2><ul>{findings}</ul>
<p class="note">La cobertura capital/capital necesario para 1 SM es un indicador experimental individual y no mide solvencia mutualizada.</p></section>
{"".join(sections)}</main>
<footer>Reporte generado localmente. Revise permisos de uso y confidencialidad antes de compartir este archivo.</footer>
</body></html>"""


def write_reports(
    frame: pd.DataFrame,
    figures: dict[str, go.Figure],
    source_name: str,
    reports_dir: str | Path,
) -> tuple[Path, Path]:
    """Guarda el informe HTML interactivo y el resumen técnico Markdown."""
    output = Path(reports_dir)
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / "exploracion.html"
    markdown_path = output / "exploracion.md"
    html_path.write_text(build_dashboard_html(frame, figures), encoding="utf-8")
    markdown_path.write_text(build_markdown_report(frame, source_name), encoding="utf-8")
    return html_path, markdown_path
