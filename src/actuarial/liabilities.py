"""Valoración mensual determinística. Tabla sintética != experiencia institucional."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Mapping
import math
import numpy as np
import pandas as pd


def finite(value: float, name: str, minimum: float | None = None) -> float:
    value = float(value)
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f"{name} inválido")
    return value


def annual_to_monthly_q(q: float) -> float:
    """Supervivencia constante dentro del año: (1-q_m)^12 = 1-q_a."""
    q = finite(q, "q anual", 0)
    if q > 1:
        raise ValueError("q anual > 1")
    return 1.0 if q == 1 else -math.expm1(math.log1p(-q) / 12)


class Mortality(Protocol):
    def annual_q(self, age: int, sex: str, year: int) -> float: ...


@dataclass(frozen=True)
class MortalityTable:
    """q por edad cumplida y sexo; '*' permite tabla unisex.

    year es el año desde valoración (0 inicial). Sin factores se usa tabla
    estacionaria; si se proporcionan deben cubrir el horizonte sin extrapolar.
    No se fuerza q=1 a edad terminal ni se completa una edad ausente.
    """
    rates: Mapping[tuple[int, str], float]
    period_factors: tuple[float, ...] = ()
    label: str = "tabla proporcionada; origen por validar"
    synthetic: bool = False

    def annual_q(self, age: int, sex: str, year: int) -> float:
        key = (age, sex) if (age, sex) in self.rates else (age, "*")
        if key not in self.rates:
            raise ValueError(f"Mortalidad sin cobertura para edad {age}, sexo {sex}")
        q = finite(self.rates[key], "q base", 0)
        if q > 1:
            raise ValueError("q base > 1")
        if self.period_factors:
            if year >= len(self.period_factors):
                raise ValueError("Factores temporales sin cobertura")
            q *= finite(self.period_factors[year], "factor temporal", 0)
        if q > 1:
            raise ValueError("q ajustado > 1")
        return q


def synthetic_mortality(multiplier: float = 1.0) -> MortalityTable:
    """Curva de juguete creciente con edad, sin relación con RV08/RV09."""
    multiplier = finite(multiplier, "multiplicador", 0)
    rates = {(age, "*"): min(0.95, multiplier * 0.004 * math.exp(0.075 * (age - 60)))
             for age in range(151)}
    return MortalityTable(rates, label=f"SINTÉTICA exponencial, multiplicador={multiplier}", synthetic=True)


@dataclass(frozen=True)
class Beneficiary:
    """Único beneficiario independiente: pago post muerte del titular.

    Fracción y tabla son obligatorias: no se presume regla legal alguna.
    Extensiones con múltiples beneficiarios requieren otro modelo de estados.
    """
    age: float
    sex: str
    fraction: float
    mortality: Mortality


@dataclass(frozen=True)
class LiabilityAssumptions:
    horizon_months: int | None = None
    terminal_age: int = 110
    annual_discount: float = 0.03
    annual_indexation: float = 0.02
    expense_fraction: float = 0.0
    expense_per_recipient_month: float = 0.0
    # Derecho devengado al inicio, desembolso al cierre de mes.
    timing: str = "accrued_start_paid_end"

    def validate(self) -> None:
        for name in ("annual_discount", "annual_indexation"):
            if finite(getattr(self, name), name) <= -1:
                raise ValueError(f"{name} debe superar -1")
        for name in ("expense_fraction", "expense_per_recipient_month"):
            finite(getattr(self, name), name, 0)
        if isinstance(self.terminal_age, bool) or not isinstance(self.terminal_age, int) or not 1 <= self.terminal_age <= 150:
            raise ValueError("Edad terminal inválida")
        if self.horizon_months is not None and (isinstance(self.horizon_months, bool) or not isinstance(self.horizon_months, int) or self.horizon_months <= 0):
            raise ValueError("Horizonte debe ser entero positivo")
        if self.timing != "accrued_start_paid_end":
            raise ValueError("Momento de devengo/pago no implementado")


@dataclass
class IndividualValuation:
    flows: pd.DataFrame
    present_value: float
    rac: float
    terminal_pending: bool
    remaining_principal_survival: float
    remaining_beneficiary_survival: float


def projection_months(age: float, assumptions: LiabilityAssumptions, beneficiary: Beneficiary | None = None) -> int:
    assumptions.validate()
    if assumptions.horizon_months is not None:
        return assumptions.horizon_months
    youngest = min(age, beneficiary.age) if beneficiary else age
    months = math.ceil((assumptions.terminal_age - youngest) * 12)
    if months <= 0:
        raise ValueError("Edad inicial alcanza/supera edad terminal; configure horizonte")
    return months


def value_individual(age: float, sex: str, capital: float, monthly_benefit: float,
                     mortality: Mortality, assumptions: LiabilityAssumptions = LiabilityAssumptions(),
                     beneficiary: Beneficiary | None = None) -> IndividualValuation:
    """VPA de derechos devengados al inicio y pagados al cierre.

    No elimina el pago del mes en que fallece el titular. Beneficiario cobra
    desde el inicio del mes siguiente a la muerte. Independencia explícita.
    RAC no es ISC ni cobertura regulatoria. VPA cero produce RAC NaN.
    """
    age = finite(age, "edad", 0)
    if age > 150:
        raise ValueError("Edad fuera de dominio")
    capital = finite(capital, "capital", 0)
    monthly_benefit = finite(monthly_benefit, "prestación", 0)
    if beneficiary:
        finite(beneficiary.age, "edad beneficiario", 0)
        if beneficiary.age > 150 or not 0 <= finite(beneficiary.fraction, "fracción", 0) <= 1:
            raise ValueError("Beneficiario inválido")
    months = projection_months(age, assumptions, beneficiary)
    principal, dependent = 1.0, 1.0 if beneficiary else 0.0
    rows = []
    for month in range(1, months + 1):
        time = (month - 1) / 12
        q = annual_to_monthly_q(mortality.annual_q(math.floor(age + time + 1e-9), sex, (month - 1) // 12))
        bq = annual_to_monthly_q(beneficiary.mortality.annual_q(math.floor(beneficiary.age + time + 1e-9), beneficiary.sex, (month - 1) // 12)) if beneficiary else 0
        index = (1 + assumptions.annual_indexation) ** time
        principal_due = monthly_benefit * index * principal
        dependent_prob = (1 - principal) * dependent if beneficiary else 0
        beneficiary_due = monthly_benefit * index * dependent_prob * beneficiary.fraction if beneficiary else 0
        benefit = principal_due + beneficiary_due
        expenses = benefit * assumptions.expense_fraction + (principal + dependent_prob) * assumptions.expense_per_recipient_month
        discount = (1 + assumptions.annual_discount) ** (-month / 12)
        rows.append(dict(month=month, principal_survival_start=principal,
            principal_survival_end=principal * (1-q), beneficiary_survival_start=dependent,
            beneficiary_survival_end=dependent * (1-bq), principal_benefit_due=principal_due,
            beneficiary_benefit_due=beneficiary_due, benefit_due=benefit, expense_due=expenses,
            discount_factor=discount, present_value=(benefit+expenses)*discount))
        principal *= 1-q
        dependent *= 1-bq
    flows = pd.DataFrame(rows)
    if not np.isfinite(flows.to_numpy(dtype=float)).all():
        raise ValueError("Valoración fuera de rango numérico")
    pv = finite(flows.present_value.sum(), "VPA", 0)
    # Beneficiario aún vivo puede cobrar más adelante, aunque titular sobreviva al corte.
    pending = monthly_benefit > 0 or assumptions.expense_per_recipient_month > 0
    pending = bool(pending and (principal > 1e-12 or (beneficiary and beneficiary.fraction > 0 and dependent > 1e-12)))
    return IndividualValuation(flows, pv, capital / pv if pv > 0 else float("nan"),
                               pending, principal, dependent)
