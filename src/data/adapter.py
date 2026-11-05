"""Adaptación en memoria, sin escrituras ni rellenos individuales inventados."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from src.data.loader import normalize_columns, load_workbook
from src.data.schema import DataMapping, ActuarialConfiguration, ISC_FIELDS, ACTUARIAL_FIELDS
from src.data.risk_catalog import RiskCatalog
from src.actuarial.eligibility import calculate_isc


@dataclass
class AdaptedData:
    frame: pd.DataFrame
    mapping: DataMapping
    actuarial: ActuarialConfiguration
    catalog: RiskCatalog
    transformations: pd.DataFrame
    missing_columns: tuple[str,...]


def adapt_frame(source: pd.DataFrame, mapping: DataMapping, catalog: RiskCatalog,
                actuarial: ActuarialConfiguration = ActuarialConfiguration()) -> AdaptedData:
    """No modifica source. Conserva solo el esquema declarado, nunca columnas extra."""
    if source.columns.duplicated().any():
        raise ValueError('Encabezados duplicados: corregir el mapeo')
    renamed=source.rename(columns=dict(mapping.columns)).copy(deep=True)
    frame=normalize_columns(renamed)
    frame=frame.reset_index(drop=True)
    fields=set(ISC_FIELDS+ACTUARIAL_FIELDS+('mesada','moneda','fecha_precios','descapitalizacion'))
    missing=tuple(sorted(set(ISC_FIELDS+ACTUARIAL_FIELDS)-set(frame.columns)))
    frame=frame[[col for col in frame if col in fields]].copy()
    for field in fields:
        if field not in frame: frame[field]=pd.NA
    log=[]
    def record(name,note,count): log.append(dict(transformation=name,description=note,records=int(count)))
    record('headers','Mapeo explícito y normalización de encabezados',len(frame))
    record('mapping_pending','Columnas configuradas ausentes en la fuente; revisar correspondencias',sum(col not in source.columns for col,target in mapping.columns))
    for col in ('capital_mas_bono','capital_necesario_sm','edad','prestacion_mensual','mesada','descapitalizacion'):
        before=frame[col]
        numeric=pd.to_numeric(before,errors='coerce').replace([np.inf,-np.inf],np.nan)
        record('numeric_'+col,'No numéricos/no finitos a nulo con alerta; sin imputación',int((before.notna() & numeric.isna()).sum()))
        if col in ('capital_mas_bono','capital_necesario_sm','prestacion_mensual','mesada','descapitalizacion'):
            numeric=numeric*mapping.amount_multiplier
        frame[col]=numeric
    if mapping.amount_multiplier!=1:
        record('units','Escalado monetario explícitamente configurado',len(frame))
    if 'fecha_corte' in missing and mapping.valuation_date is not None:
        frame['fecha_corte']=mapping.valuation_date
        record('valuation_date','Fecha global de valoración declarada; no inferida de fecha generación',len(frame))
    # Formato estricto: evita interpretar ambiguamente fechas día/mes.
    for col in ('fecha_corte','fecha_precios'):
        observed=frame[col]
        parsed=pd.to_datetime(observed,format=mapping.date_format,errors='coerce')
        frame[col+'_parse_invalid']=observed.notna() & parsed.isna()
        frame[col]=parsed
        record('date_'+col,'Parseo de fecha con formato explícito; fallos no se imputan',frame[col+'_parse_invalid'].sum())
    frame['sexo_original']=frame['sexo']
    codes=dict(mapping.sex_codes)
    frame['sexo']=frame.sexo.map(lambda v:codes.get(str(v).strip()) if pd.notna(v) else None)
    if mapping.allow_unisex:
        affected=frame.sexo.isna()
        frame.loc[affected,'sexo']='*'
        record('unisex','Hipótesis unisex explícita; no es sexo observado',affected.sum())
    if mapping.benefit_mode=='current':
        frame['prestacion_mensual']=frame['mesada']
        record('benefit_current','Mesada vigente, sin equipararla al SMMLV',len(frame))
    elif mapping.benefit_mode in {'smmlv','explicit'}:
        # Valores globales autorizados por escenario/fecha, nunca lookup externo.
        frame['prestacion_mensual']=mapping.benefit_value if mapping.benefit_value is not None else np.nan
        record('benefit_scenario','Prestación global suministrada; validar vigencia y moneda',len(frame))
    frame=calculate_isc(frame,catalog=catalog)
    # Sin deduplicación y sin fabricar identificadores.
    return AdaptedData(frame,mapping,actuarial,catalog,pd.DataFrame(log),missing)


def read_local_source(path: str | Path, mapping: DataMapping, catalog: RiskCatalog,
                      actuarial: ActuarialConfiguration = ActuarialConfiguration(), sheet_name=0) -> AdaptedData:
    """Único acceso a archivo: carga con loader en lectura; el modelo no conoce rutas.

    normalize=False permite mapeos sobre encabezados originales. Pandas recibe
    handle rb; no existe ruta de escritura al archivo de entrada.
    """
    frame=load_workbook(path,sheet_name=sheet_name,normalize=False)
    return adapt_frame(frame,mapping,catalog,actuarial)
