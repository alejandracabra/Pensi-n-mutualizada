"""Demostración fase 3: fuentes sintéticas incompletas, ningún archivo corporativo."""
from dataclasses import replace
from pathlib import Path
import json
import warnings
import pandas as pd
from src.data.adapter import adapt_frame
from src.data.schema import DataMapping, ActuarialConfiguration
from src.data.risk_catalog import DEFAULT_CATALOG
from src.data.validation import validate_adapted
from src.actuarial.liabilities import LiabilityAssumptions, synthetic_mortality, MortalityTable
from src.simulation.validated import simulate_adapted, IncompleteCohortError
from src.utils.disclosure import require_safe_output


def synthetic_incomplete_source():
    n=16
    frame=pd.DataFrame(dict(registro=[f'SYN-{k}' for k in range(n)],
        Edad=[65]*n, sexo=['F']*n, Riesgo=['VEJEZ']*n,
        capital_mas_bono=[40.0]*n,capital_necesario_sm=[100.0]*n,
        prestacion_mensual=[1.0]*n,fecha_corte=['2026-11-05']*n,
        beneficiarios_estado=['none_confirmed']*n,moneda=['ABSTRACT']*n))
    frame.loc[3,'Edad']=None
    frame.loc[4,'sexo']=None
    frame.loc[5,'beneficiarios_estado']='unavailable'
    frame.loc[7,'registro']=frame.loc[6,'registro']
    frame.loc[8,'capital_mas_bono']=-1
    frame.loc[9,'prestacion_mensual']=None
    frame.loc[10,'Riesgo']='GPM'
    frame.loc[11,'Riesgo']='RIESGO NO VALIDADO'
    frame.loc[12,'capital_necesario_sm']=0
    frame.loc[13,'fecha_corte']='2025-11-05'
    frame.loc[14,'Edad']=90
    frame.loc[15,'moneda']='USD'
    return frame


def demo_data():
    mapping=DataMapping(valuation_date='2026-11-05',prices_date='2026-11-05',
        source_currency='ABSTRACT',model_currency='ABSTRACT',observation_unit='pensionado')
    table=synthetic_mortality()
    table=MortalityTable({key:value for key,value in table.rates.items() if key[0] not in {90,91}},
        label='SINTÉTICA con hueco intencional de cobertura',synthetic=True)
    config=ActuarialConfiguration(table,LiabilityAssumptions(horizon_months=24),.02,True,True)
    return adapt_frame(synthetic_incomplete_source(),mapping,DEFAULT_CATALOG,config)


def run_demo():
    data=demo_data()
    diagnosis=validate_adapted(data)
    try:
        simulate_adapted(data)
    except IncompleteCohortError:
        blocked=True
    else:
        raise AssertionError('La cohorte incompleta debió bloquearse')
    # Opt-in exclusivo de esta demostración sintética y acompañado de conciliación.
    simulation=simulate_adapted(data,allow_partial=True)
    diagnosis.indicators['simulated']=simulation.monthly.summary['participants']
    return diagnosis,simulation,blocked


def generate_demo(output=None):
    root=Path(__file__).resolve().parents[2]
    output=require_safe_output(output or root/'reports/outputs/fase3_sintetica')
    if output.exists():
        raise FileExistsError('Usar un directorio nuevo; no sobrescribir resultados históricos')
    diagnosis,simulation,blocked=run_demo()
    output.mkdir(parents=True)
    for name,frame in [('causes',diagnosis.by_cause),('states',diagnosis.by_state),
        ('isc_reconciliation',diagnosis.isc_reconciliation),('selection',simulation.reconciliation),
        ('flows_A_partial',simulation.monthly.projection),('transformations',diagnosis.adapted.transformations)]:
        frame.to_csv(output/f'{name}.csv',index=False)
    (output/'indicators.json').write_text(json.dumps(diagnosis.indicators,indent=2),encoding='utf-8')
    tables=diagnosis.by_state.to_html(index=False)+simulation.reconciliation.to_html(index=False)+diagnosis.by_cause.to_html(index=False)
    page='<!doctype html><html lang="es"><meta charset="utf-8"><style>body{font:16px Arial;color:#0033A0;background:white;margin:40px}td,th{padding:10px;border-bottom:1px solid #4EC3E0}</style><h1>Adaptación — DATOS SINTÉTICOS</h1><p>16 filas ficticias incompletas. La ejecución íntegra se bloquea. La ejecución parcial se autoriza explícitamente solo para este ejemplo y no representa elegibilidad ni viabilidad.</p>'+tables+'<p>No se exportaron identificadores ni observaciones individuales. Los estados suman el total; las causas pueden superponerse. El VPA es truncado y la cola permanece pendiente.</p></html>'
    (output/'diagnosis.html').write_text(page,encoding='utf-8')
    return output

if __name__=='__main__':
    print(generate_demo())
