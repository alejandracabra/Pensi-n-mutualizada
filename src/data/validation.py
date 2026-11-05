"""Diagnósticos en memoria: causas superpuestas y estado principal exhaustivo."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from src.actuarial.liabilities import Beneficiary, projection_months, annual_to_monthly_q
from src.actuarial.eligibility import classified_isc, reconcile_isc
from src.data.adapter import AdaptedData

# Orden explícito. Las causas simultáneas siguen disponibles sin perderse.
STATE_PRIORITY=(
    ('identification','Identificación/unidad pendiente'),
    ('risk_excluded','No aplicable por regla ISC'),
    ('risk_pending','Riesgo pendiente de validación'),
    ('capital','Capital inválido'),
    ('isc','ISC no calculable'),
    ('age','Edad inválida o faltante'),
    ('sex','Sexo sin hipótesis apropiada'),
    ('date','Fecha de valoración/precios pendiente'),
    ('currency','Unidades monetarias pendientes'),
    ('benefit','Prestación objetivo pendiente'),
    ('beneficiaries','Beneficiarios pendientes'),
    ('assumptions','Hipótesis actuariales pendientes'),
    ('mortality','Mortalidad sin cobertura'),
)


@dataclass
class ValidationResult:
    adapted: AdaptedData
    causes: pd.DataFrame
    states: pd.Series
    by_cause: pd.DataFrame
    by_state: pd.DataFrame
    indicators: dict
    isc_reconciliation: pd.DataFrame

    @property
    def ready_mask(self):
        return self.states.eq('Preparado para valoración')


def validate_adapted(data: AdaptedData) -> ValidationResult:
    """No imputa ni omite filas. Retorna únicamente agregados si se exportan resúmenes."""
    frame=classified_isc(data.frame,catalog=data.catalog)
    data.frame=frame
    mapping,act=data.mapping,data.actuarial
    n=len(frame)
    causes=pd.DataFrame(False,index=frame.index,columns=[name for name,state in STATE_PRIORITY])
    identifiers=frame.registro
    causes['identification']=identifiers.isna() | identifiers.astype('string').str.strip().eq('').fillna(True) | identifiers.duplicated(keep=False)
    if mapping.observation_unit!='pensionado': causes['identification']=True
    causes['risk_excluded']=frame.riesgo_estado.eq('excluded')
    causes['risk_pending']=frame.riesgo_estado.isin(['unknown','missing'])
    if data.catalog.provisional and not act.allow_provisional_catalog:
        causes.loc[frame.isc_aplicable,'risk_pending']=True
    causes['capital']=frame.capital_invalido
    causes['isc']=frame.ISC.isna()
    causes['age']=frame.edad_invalida
    causes['sex']=~frame.sexo.isin(['F','M','*'])
    cut=pd.to_datetime(mapping.valuation_date,format=mapping.date_format,errors='coerce')
    prices=pd.to_datetime(mapping.prices_date,format=mapping.date_format,errors='coerce')
    causes['date']=frame.fecha_corte.isna() | frame.fecha_corte.ne(cut)
    if pd.isna(cut) or pd.isna(prices) or prices!=cut: causes['date']=True
    observed_prices=frame.fecha_precios
    causes['date'] |= observed_prices.notna() & observed_prices.ne(prices)
    for name in ('fecha_corte_parse_invalid','fecha_precios_parse_invalid'):
        if name in frame: causes['date'] |= frame[name]
    unit_ok=mapping.source_currency in {'COP','ABSTRACT'} and mapping.source_currency==mapping.model_currency
    causes['currency']=not unit_ok
    observed_currency=frame.moneda.astype('string').str.strip().str.upper()
    causes['currency'] |= observed_currency.notna() & observed_currency.ne(mapping.source_currency).fillna(True)
    causes['benefit']=frame.prestacion_mensual.isna() | frame.prestacion_mensual.lt(0)
    if mapping.benefit_mode in {'smmlv','explicit'}:
        bdate=pd.to_datetime(mapping.benefit_date,format=mapping.date_format,errors='coerce')
        if mapping.benefit_value is None or pd.isna(bdate) or bdate!=cut:
            causes['benefit']=True
    for i,row in frame.iterrows():
        state=row.beneficiarios_estado
        valid_none=isinstance(state,str) and state=='none_confirmed'
        valid_known=isinstance(state,str) and state=='known' and isinstance(row.beneficiarios,Beneficiary)
        if valid_known:
            b=row.beneficiarios
            try:
                valid_known=(math.isfinite(b.age) and 0<=b.age<=150 and math.isfinite(b.fraction) and 0<=b.fraction<=1 and b.sex in {'F','M','*'})
            except (ValueError,TypeError): valid_known=False
        # No se supone inexistencia por falta de datos; none_confirmed no admite estructura contradictoria.
        if valid_none:
            value=row.beneficiarios
            absent=value is None or value is pd.NA or (isinstance(value,float) and math.isnan(value))
            if not absent: valid_none=False
        causes.loc[i,'beneficiaries']=not (valid_none or valid_known)
    config_ok=act.authorized_for_scenario and act.assumptions is not None and act.annual_return is not None
    causes['assumptions']=not config_ok
    if act.mortality is None:
        causes['mortality']=True
    elif config_ok:
        valid_from=getattr(act.mortality,'valid_from',None)
        valid_to=getattr(act.mortality,'valid_to',None)
        valid_year=getattr(act.mortality,'valuation_year',None)
        metadata_ok=True
        if valid_from is not None:
            start=pd.to_datetime(valid_from,errors='coerce'); end=pd.to_datetime(valid_to,errors='coerce')
            metadata_ok=pd.notna(cut) and pd.notna(start) and pd.notna(end) and start<=cut<=end
        if valid_year is not None: metadata_ok=metadata_ok and pd.notna(cut) and cut.year==valid_year
        if not metadata_ok: causes['mortality']=True
        # Cobertura completa del horizonte común: no se excluye a alguien porque falte una edad futura.
        eligible=~causes[[c for c in causes if c!='mortality']].any(axis=1)
        youngest=frame.loc[eligible,'edad'].min() if eligible.any() else np.nan
        beneficiary_ages=[row.beneficiarios.age for row in frame.loc[eligible].itertuples()
                          if isinstance(row.beneficiarios,Beneficiary)]
        if beneficiary_ages: youngest=min(youngest,min(beneficiary_ages))
        months=act.assumptions.horizon_months
        if months is None and pd.notna(youngest): months=math.ceil((act.assumptions.terminal_age-youngest)*12)
        for i,row in frame.loc[eligible].iterrows():
            try:
                if months is None or months<=0: raise ValueError('Horizonte inválido')
                for m in range(months):
                    annual_to_monthly_q(act.mortality.annual_q(math.floor(row.edad+m/12+1e-9),row.sexo,m//12))
                    if isinstance(row.beneficiarios,Beneficiary):
                        b=row.beneficiarios
                        annual_to_monthly_q(b.mortality.annual_q(math.floor(b.age+m/12+1e-9),b.sex,m//12))
            except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
                causes.loc[i,'mortality']=True
    states=pd.Series('Preparado para valoración',index=frame.index,dtype='string')
    for key,label in reversed(STATE_PRIORITY): states.loc[causes[key]]=label
    by_cause=pd.DataFrame({'cause':causes.columns,'records':causes.sum().astype(int).values})
    by_cause['pct_total_read']=by_cause.records/n*100 if n else 0.0
    by_state=states.value_counts().rename_axis('state').reset_index(name='records')
    assert by_state.records.sum()==n
    minimal=~frame.capital_invalido & ~frame.denominador_invalido & ~frame.riesgo_faltante
    indicators=dict(total_read=n,minimum_schema=int(minimal.sum()),isc_calculable=int(frame.ISC.notna().sum()),
        ready=int(states.eq('Preparado para valoración').sum()),
        actuarial_pending=int(causes[['age','sex','benefit','beneficiaries','assumptions','mortality','date','currency']].any(axis=1).sum()),
        risk_pending=int(causes.risk_pending.sum()),identification_pending=int(causes.identification.sum()),
        simulated=0,
        cohort_records={name:int((frame.isc_aplicable & frame.ISC.lt(t)).sum()) for name,t in zip('ABCDE',(1,1.05,1.1,1.15,1.2))})
    indicators['cohort_records']['adicional']=int((frame.isc_aplicable & frame.ISC.ge(1) & frame.ISC.lt(1.2)).sum())
    return ValidationResult(data,causes,states,by_cause,by_state,indicators,reconcile_isc(frame))
