"""Interfaz pendiente de reglas institucionales: ninguna comparación ficticia."""
from typing import Protocol
import pandas as pd

REQUIRED_RULES = (
    "Fórmula de recálculo de mesada, periodicidad y fecha de valoración",
    "Tabla de mortalidad, mejoras y base técnica de descuento",
    "Beneficiarios, sustituciones, garantías y restricciones de pago",
    "Gastos, comisiones, rentabilidad, indexación y saldos transferibles",
    "Reglas al agotar capital y tratamiento de fallecimientos",
)

class ProgrammedWithdrawalProjector(Protocol):
    def project(self, participants: pd.DataFrame, validated_rules: dict) -> pd.DataFrame: ...


def project_programmed_withdrawal(*args, **kwargs):
    raise NotImplementedError("Pendiente de reglas institucionales validadas; ver REQUIRED_RULES")
