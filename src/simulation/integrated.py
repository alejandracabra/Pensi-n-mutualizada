"""Fase 2 reproducible: python -m src.simulation.integrated. Solo sintéticos."""
from __future__ import annotations
from dataclasses import asdict, replace
from pathlib import Path
import json
import hashlib
import platform
import subprocess
from importlib.metadata import version
import numpy as np
import pandas as pd
from src.actuarial.eligibility import (build_isc_cohorts, describe_isc_cohorts,
    calculate_isc, isc_universe_summary, isc_data_quality)
from src.actuarial.liabilities import LiabilityAssumptions, synthetic_mortality
from src.actuarial.pool import value_cohort, project_monthly_pool


def synthetic_participants() -> pd.DataFrame:
    """Unidades abstractas: 1 representa prestación mensual objetivo ilustrativa.

    Ningún importe representa un SMMLV vigente ni un pensionado real.
    Incluye intencionalmente casos de calidad y exclusiones.
    """
    ratios = np.tile([0, .4, .8, .99, 1, 1.025, 1.05, 1.075, 1.1, 1.125, 1.15, 1.175, 1.2, 1.4], 3)
    n = len(ratios)
    frame = pd.DataFrame(dict(registro=[f"SYN-{k:03d}" for k in range(n)],
        edad=[60+(k*7)%25 for k in range(n)], sexo=["F" if k%2 else "M" for k in range(n)],
        capital_mas_bono=ratios*180, capital_necesario_sm=np.full(n,180.0),
        prestacion_mensual=np.ones(n), riesgo=["VEJEZ"]*n, synthetic=True))
    extras = frame.iloc[:5].copy()
    extras['registro'] = [f"SYN-Q{k}" for k in range(5)]
    extras['riesgo'] = ['GPM','Sustitución–GPM','DESCONOCIDO','VEJEZ','VEJEZ']
    extras['capital_mas_bono'] = [100,100,100,-10,100]
    extras['capital_necesario_sm'] = [180,180,180,180,0]
    frame = pd.concat([frame,extras],ignore_index=True)
    frame['descapitalizacion'] = (frame.capital_necesario_sm-frame.capital_mas_bono).clip(lower=0)
    frame.loc[frame.riesgo.isin(['GPM','Sustitución–GPM']), 'descapitalizacion'] = 0
    return frame


def compare_cohorts(frame: pd.DataFrame, mortality, assumptions: LiabilityAssumptions,
                    annual_return: float = .02, scenario: str = 'base') -> tuple[pd.DataFrame, dict]:
    """Mismos supuestos y horizonte para cohortes; cada fila se valora una sola vez.

    Se fija horizonte común incluso si cambian las edades mínimas entre grupos.
    Devuelve flujos agregados por cohorte/régimen; no devuelve microdatos al reporte.
    """
    cohorts = build_isc_cohorts(frame)
    if assumptions.horizon_months is None:
        selected = cohorts['E']
        if selected.empty:
            horizon = 1
        else:
            horizon = max(1, int(np.ceil((assumptions.terminal_age-float(selected.edad.min()))*12)))
        assumptions = replace(assumptions,horizon_months=horizon)
    results, rows = {}, []
    for name, participants in cohorts.items():
        valuation = value_cohort(participants,mortality,assumptions)
        for regime in ('no_support','guarantee','variable'):
            result = project_monthly_pool(valuation,annual_return,regime)
            rows.append(dict(scenario=scenario,cohort=name,**result.summary))
            results[(name,regime)] = result
    return pd.DataFrame(rows), results


def run_analysis() -> dict:
    frame = synthetic_participants()
    assumptions = LiabilityAssumptions(terminal_age=110,annual_discount=.03,
        annual_indexation=.02,expense_fraction=.03)
    mortality = synthetic_mortality()
    comparison, results = compare_cohorts(frame,mortality,assumptions)
    sensitivity = [comparison]
    scenario_parameters = {'base':dict(annual_return=.02,mortality_multiplier=1.0,**asdict(assumptions))}
    cases = [
        ('menor_mortalidad',synthetic_mortality(.7),assumptions,.02,.7),
        ('rentabilidad_negativa',mortality,assumptions,-.01,1.0),
        ('mayor_indexacion',mortality,replace(assumptions,annual_indexation=.04),.02,1.0),
        ('mayores_gastos',mortality,replace(assumptions,expense_fraction=.08),.02,1.0),
        ('mayor_descuento',mortality,replace(assumptions,annual_discount=.05),.02,1.0)]
    for name, table, parameters, ret, multiplier in cases:
        summary,_ = compare_cohorts(frame,table,parameters,ret,name)
        sensitivity.append(summary)
        scenario_parameters[name] = dict(annual_return=ret,mortality_multiplier=multiplier,**asdict(parameters))
    calculated = calculate_isc(frame)
    segments = isc_universe_summary(frame)
    # No se exporta frame ni individuals. Solo agregados y supuestos genéricos.
    return dict(comparison=comparison, results=results, sensitivity=pd.concat(sensitivity,ignore_index=True),
        cohort_statistics=describe_isc_cohorts(build_isc_cohorts(frame)),
        universe=segments, quality=isc_data_quality(calculated),
        parameters=dict(synthetic=True,units='unidades abstractas, no COP ni SMMLV vigente',
            benefit_monthly=1.0,source_capital_required=180.0,
            mortality_formula='min(0.95, multiplier * 0.004 * exp(0.075*(age-60)))',
            mortality_label=mortality.label, mortality_age_range=[0,150], beneficiaries='hipótesis sin beneficiarios',
            scenario_parameters=scenario_parameters))


def generate_integrated(output: Path | None = None) -> Path:
    from src.visualization.integrated import export_figures
    from src.utils.integrated_reporting import write_integrated_reports
    output = Path(output) if output else Path(__file__).resolve().parents[2] / 'reports/outputs/integracion_sintetica'
    analysis = run_analysis()
    repository = Path(__file__).resolve().parents[2]
    hashes = {str(p.relative_to(repository)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((repository/'src').rglob('*.py'))}
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repository,text=True).strip()
    except (OSError,subprocess.CalledProcessError):
        revision = 'no disponible'
    analysis['parameters']['reproducibility'] = dict(python=platform.python_version(),
        packages={name:version(name) for name in ('numpy','pandas','matplotlib','plotly')},
        base_commit=revision, source_sha256=hashes,
        note='Los hashes identifican el código ejecutado, incluidos cambios sin commit.')
    technical = output/'technical'
    technical.mkdir(parents=True,exist_ok=True)
    (technical/'parameters.json').write_text(json.dumps(analysis['parameters'],indent=2,ensure_ascii=False),encoding='utf-8')
    for key in ('comparison','sensitivity','cohort_statistics','universe'):
        analysis[key].to_csv(technical/f'{key}.csv',index=False)
    (technical/'quality.json').write_text(json.dumps(analysis['quality'],indent=2),encoding='utf-8')
    for (cohort, regime), result in analysis['results'].items():
        result.projection.to_csv(technical/f'flows_{cohort}_{regime}.csv',index=False)
    figures = export_figures(analysis,output/'powerpoint')
    write_integrated_reports(analysis,figures,output)
    return output

if __name__ == '__main__':
    print(generate_integrated())
