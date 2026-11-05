"""Contratos de adaptación: datos individuales y supuestos globales separados."""
from dataclasses import dataclass, field
import math
from src.actuarial.liabilities import LiabilityAssumptions, Mortality
from src.data.risk_catalog import load_local_yaml

ISC_FIELDS=('capital_mas_bono','capital_necesario_sm','riesgo')
ACTUARIAL_FIELDS=('registro','fecha_corte','edad','sexo','capital_mas_bono',
                  'prestacion_mensual','beneficiarios_estado','beneficiarios')


@dataclass(frozen=True)
class DataMapping:
    # Mapeo columna fuente -> nombre interno, previo a normalización heredada.
    columns: tuple[tuple[str,str], ...] = ()
    valuation_date: str | None = None
    date_format: str = '%Y-%m-%d'
    source_currency: str | None = None
    model_currency: str | None = None
    prices_date: str | None = None
    amount_multiplier: float = 1.0
    observation_unit: str | None = None
    sex_codes: tuple[tuple[str,str], ...] = (('F','F'),('M','M'))
    allow_unisex: bool = False
    benefit_mode: str = 'provided'  # provided, current, smmlv, explicit
    benefit_value: float | None = None
    benefit_date: str | None = None

    def __post_init__(self):
        if self.benefit_mode not in {'provided','current','smmlv','explicit'}:
            raise ValueError('Modo de prestación inválido')
        if not math.isfinite(self.amount_multiplier) or self.amount_multiplier<=0:
            raise ValueError('Multiplicador monetario inválido')
        if len(dict(self.columns))!=len(self.columns) or len({b for a,b in self.columns})!=len(self.columns):
            raise ValueError('Mapeo duplicado o ambiguo')
        if len(dict(self.sex_codes))!=len(self.sex_codes) or any(v not in {'F','M','*'} for k,v in self.sex_codes):
            raise ValueError('Codificación de sexo inválida')
        if self.benefit_value is not None and (not math.isfinite(self.benefit_value) or self.benefit_value<0):
            raise ValueError('Prestación configurada inválida')

    @classmethod
    def load(cls,path):
        config=load_local_yaml(path)
        config['columns']=tuple(config.get('columns',{}).items())
        if 'sex_codes' in config: config['sex_codes']=tuple(config['sex_codes'].items())
        return cls(**config)


@dataclass(frozen=True)
class ActuarialConfiguration:
    mortality: Mortality | None = None
    assumptions: LiabilityAssumptions | None = None
    annual_return: float | None = None
    # Requerido por el adaptador; no se asume validación de una tabla externa.
    authorized_for_scenario: bool = False
    allow_provisional_catalog: bool = False

    def __post_init__(self):
        if self.assumptions is not None: self.assumptions.validate()
        if self.annual_return is not None and (not math.isfinite(self.annual_return) or self.annual_return<=-1):
            raise ValueError('Rentabilidad inválida')
