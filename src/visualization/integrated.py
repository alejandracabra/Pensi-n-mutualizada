"""Figuras agregadas SURA para fase 2, una comparación por concepto."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from src.visualization.palette import SURA_PRIMARY, SURA_SECONDARY, SURA_ACCENT, SURA_YELLOW


def export_figures(analysis: dict, output: Path) -> dict[str, Path]:
    if analysis.get('parameters',{}).get('synthetic') is not True:
        raise PermissionError('Exportación no sintética desactivada por defecto')
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    artifacts = {}

    def canvas(title,ylabel):
        fig,ax=plt.subplots(figsize=(40/3,7.5),layout='constrained')
        fig.set_facecolor('white'); ax.set_facecolor('white')
        ax.set_title(title+' — DATOS SINTÉTICOS',color=SURA_PRIMARY,fontsize=17,pad=18)
        ax.set_ylabel(ylabel); ax.spines[['top','right']].set_visible(False)
        ax.tick_params(colors=SURA_PRIMARY)
        fig.supxlabel('Unidades abstractas. Sin calibración ni beneficiarios. No demuestra viabilidad.',fontsize=10)
        return fig,ax

    def save(fig,key):
        for suffix in ('png','svg'):
            path=output/f'{key}.{suffix}'
            fig.savefig(path,dpi=300,facecolor='white')
            if suffix=='svg': artifacts[key]=path
        plt.close(fig)

    universe=analysis['universe']
    stats=analysis['cohort_statistics'].set_index('cohort')
    below=float(stats.loc['A','records'])
    additional=float(stats.loc['adicional','records'])
    non_decapitalized=float(universe.loc[universe.grupo.eq('No descapitalizada (ISC >= 1)'),'registros'].sum())
    counts=[below, additional, non_decapitalized-additional]
    fig,ax=canvas('Distribución de registros por segmentos ISC','Registros')
    ax.barh(['ISC < 1','1 ≤ ISC < 1,20','ISC ≥ 1,20'],counts,
        color=[SURA_PRIMARY,SURA_SECONDARY,SURA_ACCENT])
    ax.set_xlabel(f'Universo aplicable y calculable: {int(sum(counts))} registros. Intervalos excluyentes.')
    ax.invert_yaxis(); save(fig,'01_isc')
    summary=analysis['comparison'].query("regime == 'no_support'")
    x=np.arange(len(summary)); fig,ax=canvas('Capital aportado y VPA modelado','Unidades abstractas')
    ax.bar(x-.18,summary.initial_capital,.36,label='Capital aportado',color=SURA_PRIMARY)
    ax.bar(x+.18,summary.initial_liability,.36,label='VPA prestaciones y gastos',color=SURA_SECONDARY)
    ax.set_xticks(x,summary.cohort); ax.set_xlabel('Cohorte exploratoria'); ax.legend(frameon=False)
    save(fig,'02_capital_obligaciones')
    fig,ax=canvas('Cobertura actuarial inicial','Capital / VPA modelado')
    ax.bar(summary.cohort,summary.initial_coverage,color=SURA_PRIMARY)
    ax.axhline(1,color=SURA_SECONDARY,linestyle='--',label='Referencia 1 (no regulatoria)')
    ax.set_xlabel('Cohorte exploratoria'); ax.legend(frameon=False); save(fig,'03_cobertura')
    # A: cohorte ISC < 1. No se selecciona por desempeño favorable.
    flows=analysis['results'][('A','no_support')].projection
    guarantee=analysis['results'][('A','guarantee')].projection
    fig,ax=canvas('Activos de la bolsa A sin respaldo','Unidades abstractas')
    ax.plot(flows.month,flows.closing_assets,color=SURA_PRIMARY)
    ax.set_xlabel('Mes'); save(fig,'04_activos')
    fig,ax=canvas('Prestaciones A: debidas y financiadas por la bolsa','Unidades abstractas mensuales')
    ax.plot(flows.month,flows.benefit_due,label='Debidas',color=SURA_PRIMARY)
    ax.plot(flows.month,flows.benefits_funded_by_pool,label='Financiadas por bolsa',color=SURA_SECONDARY)
    ax.set_xlabel('Mes'); ax.legend(frameon=False); save(fig,'05_prestaciones')
    fig,ax=canvas('Respaldo externo acumulado A: garantía hipotética','Unidades abstractas')
    ax.plot(guarantee.month,guarantee.external_support.cumsum(),label='Con garantía',color=SURA_PRIMARY)
    ax.plot(flows.month,flows.external_support.cumsum(),label='Sin respaldo externo',color=SURA_SECONDARY)
    ax.set_xlabel('Mes'); ax.legend(frameon=False); save(fig,'06_respaldo')
    sensitivity=analysis['sensitivity'].query("cohort == 'A' and regime == 'guarantee'")
    labels={'base':'Base','menor_mortalidad':'Menor mortalidad','rentabilidad_negativa':'Rendimiento negativo',
            'mayor_indexacion':'Mayor indexación','mayores_gastos':'Mayores gastos','mayor_descuento':'Mayor descuento'}
    fig,ax=canvas('Sensibilidad del VPA del respaldo A','Unidades abstractas descontadas')
    ax.barh([labels[s] for s in sensitivity.scenario],sensitivity.external_support_pv,color=SURA_PRIMARY)
    ax.invert_yaxis(); save(fig,'07_sensibilidad')
    return artifacts
