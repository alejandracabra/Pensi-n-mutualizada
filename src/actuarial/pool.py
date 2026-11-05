"""Bolsa cerrada determinística de demostración. Sin calibración corporativa."""
from dataclasses import dataclass
import math
import pandas as pd

@dataclass(frozen=True)
class DemographicParameters:
    members: int = 100
    initial_age: int = 65

@dataclass(frozen=True)
class FinancialParameters:
    capital_per_member: float = 100.0
    annual_return: float = 0.02
    annual_expense_rate: float = 0.005
    annual_indexation: float = 0.02

@dataclass(frozen=True)
class ActuarialParameters:
    annual_payment_per_survivor: float = 8.0
    # Probabilidades anuales de juguete, NO tabla de mortalidad.
    annual_death_probabilities: tuple[float, ...] = (0.02,) * 30


def project_pool(demographic=DemographicParameters(), financial=FinancialParameters(),
                 actuarial=ActuarialParameters()) -> pd.DataFrame:
    """Rinde al inicio; muertes esperadas; pagos al cierre a supervivientes.

    Pagos y gastos se prorratean si faltan activos. No hay deuda ni aportes
    posteriores; no se retiran saldos al fallecer. Se conserva la demanda
    impagada por periodo (sin acumularla como deuda). Unidades abstractas.
    """
    d, f, a = demographic, financial, actuarial
    if isinstance(d.members, bool) or not isinstance(d.members, int) or d.members <= 0:
        raise ValueError("members debe ser entero positivo")
    if isinstance(d.initial_age, bool) or not isinstance(d.initial_age, int) or not 0 <= d.initial_age <= 120:
        raise ValueError("initial_age debe estar entre 0 y 120")
    numbers = [f.capital_per_member, f.annual_return, f.annual_expense_rate,
               f.annual_indexation, a.annual_payment_per_survivor]
    if not all(math.isfinite(x) for x in numbers):
        raise ValueError("Parámetros no finitos")
    if f.capital_per_member < 0 or a.annual_payment_per_survivor < 0:
        raise ValueError("Capital y mesada no negativos")
    if f.annual_return <= -1 or f.annual_indexation <= -1 or not 0 <= f.annual_expense_rate <= 1:
        raise ValueError("Tasas fuera de dominio")
    qs = a.annual_death_probabilities
    if not qs or any(not math.isfinite(q) or not 0 <= q <= 1 for q in qs):
        raise ValueError("Se requiere una secuencia de probabilidades en [0, 1]")
    members, assets = float(d.members), d.members * f.capital_per_member
    rows = []
    for year, q in enumerate(qs, 1):
        opening_members, opening = members, assets
        deaths = opening_members * q
        members = opening_members - deaths
        investment = opening * f.annual_return
        available = opening + investment
        expense_due = available * f.annual_expense_rate
        benefit_due = members * a.annual_payment_per_survivor * (1 + f.annual_indexation) ** (year - 1)
        demand = benefit_due + expense_due
        if not all(math.isfinite(x) for x in [available, demand]):
            raise ValueError("Proyección fuera de rango numérico")
        factor = min(1.0, available / demand) if demand else 1.0
        paid, expenses = benefit_due * factor, expense_due * factor
        assets = max(0.0, available - paid - expenses)
        rows.append(dict(year=year, age=d.initial_age + year, opening_members=opening_members,
            expected_deaths=deaths, closing_members=members, opening_assets=opening,
            investment_income=investment, benefit_due=benefit_due, benefits_paid=paid,
            expense_due=expense_due, expenses_paid=expenses, closing_assets=assets,
            unpaid_benefits=benefit_due-paid, unpaid_expenses=expense_due-expenses,
            payment_ratio=factor, synthetic=True))
    return pd.DataFrame(rows)
