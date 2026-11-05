"""Ejecutar con python -m src.simulation.pilot. Solo datos sintéticos."""
from dataclasses import asdict
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.actuarial.pool import (project_pool, DemographicParameters,
    FinancialParameters, ActuarialParameters)
from src.visualization.palette import SURA_PRIMARY, SURA_SECONDARY


def generate_pilot(output: Path | None = None) -> Path:
    output = Path(output) if output else Path(__file__).resolve().parents[2] / "reports/outputs/piloto_sintetico"
    technical, slides = output / "technical", output / "powerpoint"
    technical.mkdir(parents=True, exist_ok=True); slides.mkdir(parents=True, exist_ok=True)
    d, f, a = DemographicParameters(), FinancialParameters(), ActuarialParameters()
    projection = project_pool(d, f, a)
    (technical / "parameters.json").write_text(json.dumps(dict(synthetic=True,
        demographic=asdict(d), financial=asdict(f), actuarial=asdict(a)), indent=2), encoding="utf-8")
    projection.to_csv(technical / "flows.csv", index=False)
    shortfall = projection.loc[projection.unpaid_benefits > 1e-10, "year"]
    (technical / "report.md").write_text(
        "# Piloto — DATOS SINTÉTICOS\n\nNo corresponde a resultados de Protección.\n\n"
        f"Primer año con prestación impagada: {int(shortfall.iloc[0]) if len(shortfall) else 'no observado en el horizonte'}.\n\n"
        "No implica viabilidad. Ver parámetros, flujos y docs/piloto_mutualizacion.md. "
        "Sin tablas calibradas ni beneficiarios individuales; quedan obligaciones fuera del horizonte.\n", encoding="utf-8")
    for key, title, columns, unit in [
        ("assets", "Activos de la bolsa", ["closing_assets"], "Unidades monetarias abstractas"),
        ("survivors", "Supervivientes esperados", ["closing_members"], "Personas esperadas"),
        ("benefits", "Prestaciones requeridas y pagadas", ["benefit_due", "benefits_paid"], "Unidades monetarias abstractas"),
        ("shortfall", "Prestaciones no pagadas", ["unpaid_benefits"], "Unidades monetarias abstractas")]:
        fig, ax = plt.subplots(figsize=(40/3, 7.5), layout="constrained")
        fig.set_facecolor("white"); ax.set_facecolor("white")
        labels = {"closing_assets":"Activos al cierre", "closing_members":"Supervivientes",
            "benefit_due":"Prestación requerida", "benefits_paid":"Prestación pagada", "unpaid_benefits":"Impago anual"}
        for column, color in zip(columns, [SURA_PRIMARY, SURA_SECONDARY]):
            ax.plot(projection.year, projection[column], label=labels[column], color=color, linewidth=2.5)
        ax.set(title=title + " — DATOS SINTÉTICOS", xlabel="Año", ylabel=unit)
        ax.title.set_color(SURA_PRIMARY); ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.supxlabel("Ejemplo académico; sin mortalidad calibrada ni beneficiarios. No evalúa viabilidad.", fontsize=10)
        fig.savefig(slides / (key + ".png"), dpi=300, facecolor="white")
        fig.savefig(slides / (key + ".svg"), facecolor="white")
        plt.close(fig)
    return output

if __name__ == "__main__":
    print(generate_pilot())
