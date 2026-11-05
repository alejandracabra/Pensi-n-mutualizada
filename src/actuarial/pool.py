"""Bolsa cerrada determinística de demostración. Sin calibración corporativa."""
from dataclasses import dataclass, replace
import numpy as np
from src.actuarial.liabilities import (LiabilityAssumptions,
    Mortality, value_individual, projection_months, finite)
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


# La API anual project_pool se conserva como regresión del piloto histórico.
# La integración de fase 2 utiliza exclusivamente esta API mensual.


@dataclass
class CohortValuation:
    """Detalle individual solo en memoria; exportaciones exclusivamente agregadas."""
    initial_capital: float
    initial_liability: float
    initial_coverage: float
    individuals: dict
    flows: pd.DataFrame
    assumptions: LiabilityAssumptions
    terminal_pending: bool


def value_cohort(participants: pd.DataFrame, mortality: Mortality,
                 assumptions: LiabilityAssumptions = LiabilityAssumptions(),
                 beneficiaries: dict | None = None) -> CohortValuation:
    """Una fila por participante, registro único, capital y prestación individuales.

    beneficiaries=None declara explícitamente una hipótesis sin beneficiarios;
    no infiere su ausencia a partir de campos corporativos faltantes.
    """
    columns = {"registro", "edad", "sexo", "capital_mas_bono", "prestacion_mensual"}
    if not columns.issubset(participants):
        raise ValueError(f"Faltan variables para valorar: {sorted(columns-set(participants))}")
    if participants.registro.isna().any() or participants.registro.duplicated().any():
        raise ValueError("registro faltante/duplicado")
    if participants.sexo.isna().any():
        raise ValueError("sexo faltante: declarar unisex explícitamente si corresponde")
    beneficiaries = {} if beneficiaries is None else beneficiaries
    if not set(beneficiaries).issubset(set(participants.registro)):
        raise ValueError("Beneficiarios sin titular en la cohorte")
    assumptions.validate()
    months = assumptions.horizon_months
    if months is None:
        months = max((projection_months(finite(row.edad, "edad", 0), assumptions,
                      beneficiaries.get(row.registro)) for row in participants.itertuples()), default=1)
    common = replace(assumptions, horizon_months=months)
    individuals = {}
    for row in participants.itertuples():
        individuals[row.registro] = value_individual(row.edad, str(row.sexo),
            row.capital_mas_bono, row.prestacion_mensual, mortality, common,
            beneficiaries.get(row.registro))
    flows = pd.DataFrame({"month": np.arange(1, months+1)})
    for column in ("benefit_due", "expense_due", "principal_survival_start", "principal_survival_end",
                   "beneficiary_benefit_due"):
        flows[column] = sum((v.flows[column].to_numpy() for v in individuals.values()), np.zeros(months))
    capital = float(pd.to_numeric(participants.capital_mas_bono, errors="raise").sum())
    liability = sum(v.present_value for v in individuals.values())
    finite(capital, "capital agregado", 0)
    finite(liability, "VPA agregado", 0)
    return CohortValuation(capital, liability, capital/liability if liability > 0 else float("nan"),
        individuals, flows, common, any(v.terminal_pending for v in individuals.values()))


@dataclass
class MonthlyPoolResult:
    projection: pd.DataFrame
    summary: dict


def project_monthly_pool(valuation: CohortValuation, annual_return: float = 0.02,
                         regime: str = "no_support") -> MonthlyPoolResult:
    """Sin respaldo, garantía hipotética o prestación variable identificada.

    Mismo devengo, gastos, descuento e indexación que la valoración. Las
    insuficiencias sin garantía se prorratean entre pagos y gastos. Se mantiene
    un registro nominal acumulado de impagos sin intereses; no se vuelve a
    solicitar su pago en periodos posteriores. Reserva solo del horizonte.
    """
    if regime not in {"no_support", "guarantee", "variable"}:
        raise ValueError("Régimen desconocido")
    annual_return = finite(annual_return, "rentabilidad")
    if annual_return <= -1:
        raise ValueError("Rentabilidad debe superar -1")
    monthly_return = math.expm1(math.log1p(annual_return)/12)
    discount = (1+valuation.assumptions.annual_discount)**(1/12)
    flows = valuation.flows
    demand = flows.benefit_due + flows.expense_due
    future = np.zeros(len(flows))
    reserve = 0.0
    for k in range(len(flows)-1, -1, -1):
        future[k] = reserve
        reserve = (float(demand.iloc[k])+reserve)/discount
    if not math.isclose(reserve, valuation.initial_liability, rel_tol=1e-9, abs_tol=1e-8):
        raise ValueError("Flujos y obligación inicial no concilian")
    assets, arrears = valuation.initial_capital, 0.0
    rows = []
    for k, row in enumerate(flows.itertuples()):
        opening = assets
        income = opening*monthly_return
        available = max(0.0, opening+income)
        due = float(row.benefit_due+row.expense_due)
        required_support = max(0.0, due-available)
        external_support = required_support if regime == "guarantee" else 0.0
        factor = min(1.0, available/due) if due > 0 else 1.0
        funded_benefit, funded_expense = row.benefit_due*factor, row.expense_due*factor
        benefit_paid = row.benefit_due if regime == "guarantee" else funded_benefit
        expense_paid = row.expense_due if regime == "guarantee" else funded_expense
        unpaid_benefit, unpaid_expense = row.benefit_due-benefit_paid, row.expense_due-expense_paid
        arrears += unpaid_benefit+unpaid_expense
        assets = max(0.0, opening+income+external_support-benefit_paid-expense_paid)
        rows.append(dict(month=row.month, opening_assets=opening, investment_income=income,
            benefit_due=row.benefit_due, benefits_funded_by_pool=funded_benefit,
            benefits_paid=benefit_paid, expense_due=row.expense_due, expenses_funded_by_pool=funded_expense,
            expenses_paid=expense_paid, required_support=required_support, external_support=external_support,
            closing_assets=assets, unpaid_benefits=unpaid_benefit, unpaid_expenses=unpaid_expense,
            cumulative_unpaid=arrears, future_liability_in_horizon=future[k],
            pending_obligations=arrears+future[k], future_reserve_gap=max(0.0, future[k]-assets),
            expected_survivors=row.principal_survival_end,
            beneficiary_benefit_due=row.beneficiary_benefit_due))
    projection = pd.DataFrame(rows)
    pv_factors = (1+valuation.assumptions.annual_discount)**(-projection.month/12)
    insufficient = projection.loc[projection.required_support > 1e-9, "month"]
    summary = dict(regime=regime, participants=len(valuation.individuals),
        initial_capital=valuation.initial_capital, initial_liability=valuation.initial_liability,
        initial_coverage=valuation.initial_coverage,
        initial_funding_gap=max(0.0, valuation.initial_liability-valuation.initial_capital),
        first_insufficiency_month=int(insufficient.iloc[0]) if len(insufficient) else None,
        required_support_total=float(projection.required_support.sum()),
        required_support_pv=float((projection.required_support*pv_factors).sum()),
        external_support_total=float(projection.external_support.sum()),
        external_support_pv=float((projection.external_support*pv_factors).sum()),
        final_assets=float(projection.closing_assets.iloc[-1]),
        unpaid_total=float(projection.cumulative_unpaid.iloc[-1]),
        remaining_expected_survivors=float(projection.expected_survivors.iloc[-1]),
        terminal_pending=valuation.terminal_pending,
        obligations_after_horizon_vpa=float('nan') if valuation.terminal_pending else 0.0,
        remaining_beneficiary_survival_sum=sum(v.remaining_beneficiary_survival for v in valuation.individuals.values()),
        terminal_diagnosis=('VPA truncado: quedan vidas con derechos potenciales; cola no valorada'
            if valuation.terminal_pending else 'Sin derechos futuros identificados bajo las hipótesis'),
        horizon_months=len(flows))
    return MonthlyPoolResult(projection, summary)
