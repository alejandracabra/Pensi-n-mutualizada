"""Fuente única de aplicabilidad ISC; ejemplos provisionales, sin catálogo inferido."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import unicodedata
import pandas as pd
import yaml

EXCLUDED_RISKS = frozenset({'GPM', 'SUSTITUCION - GPM'})
PROVISIONAL_RISKS = frozenset({'VEJEZ','INVALIDEZ','SOBREVIVENCIA','SUSTITUCION'})


def normalize_risk(value: object) -> str:
    if pd.isna(value):
        return ''
    text=unicodedata.normalize('NFKD',str(value).upper())
    text=''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[‐‑‒–—−-]+',' - ',text).split())


def load_local_yaml(path: str | Path) -> dict:
    """Solo lectura. Dentro del repo se permiten únicamente ejemplos versionados."""
    path=Path(path).resolve()
    root=Path(__file__).resolve().parents[2]
    if root in path.parents and not path.name.endswith('.example.yaml'):
        raise ValueError('La configuración local autorizada debe estar fuera del repositorio')
    with path.open('rb') as stream:
        value=yaml.safe_load(stream)
    if not isinstance(value,dict):
        raise ValueError('Configuración YAML debe ser un objeto')
    return value


@dataclass(frozen=True)
class RiskCatalog:
    # Pares (categoría canónica, aplicabilidad); aliases (variante, canónica).
    categories: tuple[tuple[str, bool], ...]
    aliases: tuple[tuple[str, str], ...] = ()
    provisional: bool = True
    version: str = 'provisional-v1'

    def __post_init__(self):
        rules={}
        for name,applicable in self.categories:
            key=normalize_risk(name)
            if not key or key in rules or not isinstance(applicable,bool):
                raise ValueError('Categoría vacía, repetida o regla no booleana')
            if key in EXCLUDED_RISKS and applicable:
                raise ValueError('GPM y Sustitución-GPM no pueden ser aplicables')
            rules[key]=applicable
        rules.update({key:False for key in EXCLUDED_RISKS})
        aliases={}
        for name,target in self.aliases:
            key,target=normalize_risk(name),normalize_risk(target)
            if not key or target not in rules or key in rules or key in aliases:
                raise ValueError('Alias ambiguo o destino no declarado')
            aliases[key]=target
        object.__setattr__(self,'categories',tuple(sorted(rules.items())))
        object.__setattr__(self,'aliases',tuple(sorted(aliases.items())))

    @property
    def fingerprint(self) -> str:
        payload=json.dumps([self.categories,self.aliases],ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def classify(self, value: object) -> tuple[str,str]:
        key=normalize_risk(value)
        if not key: return key,'missing'
        key=dict(self.aliases).get(key,key)
        rules=dict(self.categories)
        if key not in rules: return key,'unknown'
        return key,'applicable' if rules[key] else 'excluded'

    @classmethod
    def from_mapping(cls, config: dict):
        categories=config.get('categories',{})
        aliases=config.get('aliases',{})
        if not isinstance(categories,dict) or not isinstance(aliases,dict):
            raise ValueError('Catálogo inválido')
        if not isinstance(config.get('provisional',True),bool):
            raise ValueError('provisional debe ser booleano')
        return cls(tuple(categories.items()),tuple(aliases.items()),config.get('provisional',True),str(config.get('version','sin-version')))

    @classmethod
    def load(cls,path):
        return cls.from_mapping(load_local_yaml(path))


DEFAULT_CATALOG=RiskCatalog(tuple((key,True) for key in PROVISIONAL_RISKS))
