"""Control conservador de divulgación: un agregado no es autorización de publicación."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DisclosurePolicy:
    min_cell: int = 10
    # Revisión local explícita de la familia completa de salidas, no por archivo.
    approved_for_release: bool = False

    def __post_init__(self):
        if isinstance(self.min_cell,bool) or not isinstance(self.min_cell,int) or self.min_cell<2:
            raise ValueError('Umbral de supresión debe ser entero >=2')


def disclosure_decision(total, counts, cohort_counts, policy=DisclosurePolicy()):
    """Revisa celdas, complementos y átomos por diferencias entre cohortes.

    Si falla, se suprime TODO el paquete (tablas, totales relacionados y gráficas),
    sin mostrar valores que reconstruyan una celda. No garantiza anonimato:
    cruces/otras publicaciones y conocimiento externo requieren revisión humana.
    """
    if not policy.approved_for_release:
        return False,'Divulgación no autorizada: salida bloqueada por defecto'
    values=list(counts)+list(cohort_counts.values())+[total]
    if any(v<0 or int(v)!=v or v>total for v in values):
        return False,'Conciliación de agregados inválida'
    candidates=values+[total-v for v in values]
    nested=[cohort_counts[k] for k in 'ABCDE' if k in cohort_counts]
    if nested!=sorted(nested): return False,'Cohortes no anidadas'
    candidates += [b-a for a,b in zip([0]+nested,nested)]
    if any(0<v<policy.min_cell for v in candidates):
        return False,'Paquete suprimido por celdas pequeñas o reconstrucción por diferencias'
    return True,'Revisión de umbrales aprobada; no sustituye revisión de divulgación contextual'


def require_safe_output(path):
    """Exportadores nuevos solo bajo reports/outputs; nunca escriben en data/raw."""
    path=Path(path).resolve()
    root=Path(__file__).resolve().parents[2]
    allowed=(root/'reports/outputs').resolve()
    if allowed not in path.parents or path==allowed:
        raise ValueError('Usar un subdirectorio de reports/outputs, excluido de Git')
    return path
