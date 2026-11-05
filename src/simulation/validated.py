"""Frontera segura modelo/datos: solo memoria; nunca lee archivos ni exporta detalle."""
from dataclasses import dataclass, replace
import warnings
import math
import pandas as pd
from src.data.adapter import AdaptedData, adapt_frame
from src.data.validation import validate_adapted
from src.actuarial.pool import value_cohort, project_monthly_pool
from src.actuarial.liabilities import Beneficiary
from src.actuarial.eligibility import DEFAULT_ISC_THRESHOLDS


class IncompleteCohortError(ValueError):
    def __init__(self,reconciliation,by_cause):
        super().__init__('Cohorte incompleta: consulte conciliación y causas agregadas; no se simuló')
        self.reconciliation=reconciliation
        self.by_cause=by_cause


@dataclass
class ValidatedSimulation:
    reconciliation: pd.DataFrame
    exclusion_causes: pd.DataFrame
    monthly: object
    diagnosis: object


def simulate_adapted(data: AdaptedData, cohort='A', regime='no_support', *, allow_partial=False) -> ValidatedSimulation:
    """Revalida en cada llamada. Parcial requiere opt-in y genera advertencia y conciliación."""
    diagnosis=validate_adapted(data)
    frame=diagnosis.adapted.frame
    if cohort=='adicional': selected=frame.isc_aplicable & frame.ISC.ge(1) & frame.ISC.lt(1.2)
    elif cohort in 'ABCDE' and len(cohort)==1:
        selected=frame.isc_aplicable & frame.ISC.lt(DEFAULT_ISC_THRESHOLDS['ABCDE'.index(cohort)])
    else: raise ValueError('Cohorte desconocida')
    selected=selected.fillna(False)
    ready=selected & diagnosis.ready_mask
    excluded=selected & ~diagnosis.ready_mask
    n,nready=int(selected.sum()),int(ready.sum())
    rec=pd.DataFrame([dict(cohort=cohort,selected=n,ready=nready,pending=n-nready,
        excluded_pct_selected=(n-nready)/n*100 if n else 0.0,valued=0,simulated=0)])
    causes=diagnosis.causes.loc[excluded].sum().rename_axis('cause').reset_index(name='records')
    causes['pct_selected']=causes.records/n*100 if n else 0.0
    if excluded.any() and not allow_partial: raise IncompleteCohortError(rec,causes)
    if excluded.any(): warnings.warn('Ejecución parcial autorizada explícitamente; revisar conciliación agregada',UserWarning)
    act=data.actuarial
    if act.mortality is None or act.assumptions is None or act.annual_return is None or not act.authorized_for_scenario:
        raise IncompleteCohortError(rec,causes)
    participants=frame.loc[ready].copy()
    beneficiaries={row.registro:row.beneficiarios for row in participants.itertuples() if isinstance(row.beneficiarios,Beneficiary)}
    # Igual horizonte que el validado, incluyendo las vidas dependientes.
    assumptions=act.assumptions
    if assumptions.horizon_months is None:
        all_ready=frame.loc[diagnosis.ready_mask]
        ages=list(all_ready.edad)+[b.age for b in all_ready.beneficiarios if isinstance(b,Beneficiary)]
        months=math.ceil((assumptions.terminal_age-min(ages))*12) if ages else 1
        assumptions=replace(assumptions,horizon_months=months)
    valuation=value_cohort(participants,act.mortality,assumptions,beneficiaries)
    monthly=project_monthly_pool(valuation,act.annual_return,regime)
    valued=len(valuation.individuals); simulated=monthly.summary['participants']
    if valued!=nready or valued!=simulated: raise RuntimeError('Conciliación de participantes fallida')
    if not math.isclose(valuation.initial_capital,float(participants.capital_mas_bono.sum()),abs_tol=1e-8):
        raise RuntimeError('Capital inicial no concilia')
    rec.loc[0,['valued','simulated']]=[valued,simulated]
    diagnosis.indicators['simulated']=simulated
    return ValidatedSimulation(rec,causes,monthly,diagnosis)


def simulate_validated_frame(frame, mapping, catalog, actuarial, **kwargs):
    """Entrada DataFrame sin rutas; adapta/revalida, nunca acepta una bandera ready del caller."""
    return simulate_adapted(adapt_frame(frame,mapping,catalog,actuarial),**kwargs)
