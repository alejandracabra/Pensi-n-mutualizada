"""Tabla autorizada suministrada en memoria; no descarga, extrapola ni calibra."""
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType
import math
import pandas as pd
from src.actuarial.liabilities import finite


@dataclass(frozen=True)
class PeriodMortalityTable:
    rates: tuple[tuple[int,str,int,float], ...]
    valuation_year: int
    source: str
    version: str
    valid_from: str
    valid_to: str
    synthetic: bool = False

    @cached_property
    def _rates_by_key(self):
        return MappingProxyType({(a,s,p):q for a,s,p,q in self.rates})

    def annual_q(self,age,sex,year):
        rates=self._rates_by_key
        period=self.valuation_year+year
        key=(age,sex,period) if (age,sex,period) in rates else (age,'*',period)
        if key not in rates: raise ValueError('Tabla sin cobertura de edad/sexo/período solicitado')
        return rates[key]


def mortality_from_frame(frame, *, valuation_year, source, version, valid_from, valid_to, synthetic=False):
    required={'age','sex','period','annual_q'}
    if not required.issubset(frame): raise ValueError('Faltan columnas de tabla de mortalidad')
    if not source or not version: raise ValueError('Fuente y versión de mortalidad requeridas')
    start,end=pd.to_datetime(valid_from,errors='coerce'),pd.to_datetime(valid_to,errors='coerce')
    if pd.isna(start) or pd.isna(end) or start>end: raise ValueError('Vigencia de tabla inválida')
    if isinstance(valuation_year,bool) or not isinstance(valuation_year,int): raise ValueError('Año de valoración inválido')
    rows=[]; keys=set()
    for row in frame.to_dict('records'):
        age=finite(row['age'],'edad mortalidad',0); period=finite(row['period'],'período',0)
        q=finite(row['annual_q'],'q anual',0)
        factor=finite(row.get('improvement_factor',1.0),'factor de mejoramiento',0)
        if age!=int(age) or age>150 or period!=int(period) or q>1 or q*factor>1:
            raise ValueError('Dominio de tabla inválido')
        sex=str(row['sex'])
        if sex not in {'F','M','*'}: raise ValueError('Codificación de sexo de mortalidad inválida')
        key=(int(age),sex,int(period))
        if key in keys: raise ValueError('Claves duplicadas en mortalidad')
        keys.add(key); rows.append((*key,q*factor))
    return PeriodMortalityTable(tuple(rows),valuation_year,str(source),str(version),str(valid_from),str(valid_to),synthetic)
