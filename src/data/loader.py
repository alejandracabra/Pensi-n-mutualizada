"""Lectura segura y normalización de la base de control de saldos."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


_COLUMN_ALIASES = {
    "": "registro",
    "registro": "registro",
    "riesgo": "riesgo",
    "riesgo 3": "riesgo_3",
    "mesada": "mesada",
    "rango de mesada": "rango_mesada",
    "nmesadas": "numero_mesadas",
    "capital": "capital",
    "capital bono": "capital_mas_bono",
    "capital mes anterior": "capital_mes_anterior",
    "edad": "edad",
    "fn1": "fecha_nacimiento",
    "sexo1": "sexo",
    "tipo1": "tipo",
    "estado1": "estado",
    "fecha de generacion": "fecha_generacion",
    "fechasiniestro": "fecha_siniestro",
    "capital necesario sm": "capital_necesario_sm",
    "capital necesario 1 3 sm": "capital_necesario_1_3_sm",
    "capital necesario def": "capital_necesario_def",
    "descapitalizado": "descapitalizado",
    "descapitalizacion": "descapitalizacion",
    "desfinanciado": "desfinanciado",
    "desfinanciacion": "desfinanciacion",
    "expectativa de vida": "expectativa_vida",
}


def _normalize_header(value: object) -> str:
    """Normaliza encabezados Excel acentuados, con espacios o mal codificados."""
    text = str(value).strip().lower().replace("\ufffd", "o")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Asigna nombres estables a columnas conocidas y conserva las restantes."""
    result = frame.copy()
    renamed: dict[object, str] = {}
    used: set[str] = set()

    for column in result.columns:
        normalized = _normalize_header(column)
        name = _COLUMN_ALIASES.get(normalized, normalized.replace(" ", "_"))
        if not name:
            name = "columna_sin_nombre"
        if name in used:
            raise ValueError(f"El encabezado {column!r} duplica la columna normalizada {name!r}.")
        renamed[column] = name
        used.add(name)

    return result.rename(columns=renamed)


def find_workbook(
    project_root: str | Path | None = None,
    filename: str = "Base_Proyecto.xlsx",
) -> Path:
    """Busca el Excel en las ubicaciones convencionales sin recorrer todo el disco."""
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    candidates = (
        root / "data" / "raw" / filename,
        root / filename,
        root.parent / "data" / "raw" / filename,
        root.parent / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        f"No se encontró {filename}. Rutas revisadas:\n{checked}"
    )


def load_workbook(
    path: str | Path | None = None,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """Carga la hoja solicitada del Excel y devuelve encabezados normalizados."""
    workbook_path = Path(path) if path is not None else find_workbook()
    if not workbook_path.is_file():
        raise FileNotFoundError(f"No existe el archivo de datos: {workbook_path}")

    frame = pd.read_excel(workbook_path, sheet_name=sheet_name, engine="openpyxl")
    if frame.empty:
        raise ValueError(f"La hoja {sheet_name!r} de {workbook_path.name} no contiene registros.")
    return normalize_columns(frame)
