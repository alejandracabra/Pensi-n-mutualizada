"""Ocho secciones ejecutivas; detalle de regímenes solo en anexo técnico."""
from pathlib import Path
import base64
import html
import json

LIMITATIONS=(
    'Solo datos sintéticos; no son resultados observados de Protección. '
    'Mortalidad no calibrada. La ausencia de beneficiarios se declara como hipótesis, no se infiere. '
    'Existe valoración terminal pendiente cuando quedan vidas con derechos: el VPA puede estar truncado. '
    'La cobertura no es solvencia regulatoria. No demuestra viabilidad ni autoriza garantías. '
    'Retiro programado real, dependencia entre vidas y múltiples beneficiarios permanecen pendientes.')

METRICS={
    'Activos iniciales':'Suma de capitales aportados; no incluye aportes futuros.',
    'VPA modelado':'Prestaciones y gastos descontados solo dentro del horizonte.',
    'Brecha actuarial inicial':'max(VPA modelado - activos iniciales, 0).',
    'Reserva prospectiva':'VPA al cierre de cada mes de obligaciones posteriores dentro del horizonte.',
    'Faltante de caja':'Pago y gastos del mes no cubiertos por activos disponibles.',
    'Aportes externos':'Recursos efectivamente inyectados en la garantía hipotética; no son reserva ni capital inicial requerido.',
    'VPA de aportes':'Aportes proyectados descontados; depende de la rentabilidad de activos y del descuento.',
    'Cola actuarial':'Derechos potenciales posteriores al horizonte, aún no valorados; nunca se asigna cero por desconocimiento.'}


def report_html(analysis: dict, figures: dict[str,Path], technical=False) -> str:
    """Compatibilidad sintética. Salidas no sintéticas bloqueadas por defecto.

    Para información local autorizada usar validated_report con política de
    divulgación explícita; nunca pasar microdatos a esta función.
    """
    if analysis.get('parameters',{}).get('synthetic') is not True:
        return '<html lang="es"><meta charset="utf-8"><p>Salida bloqueada: revisión de divulgación requerida.</p></html>'
    summary=analysis['comparison']
    reference='no_support'
    base=summary.loc[summary.regime.eq(reference)]
    labels={'cohort':'Cohorte','regime':'Régimen','participants':'Registros',
        'initial_capital':'Activos iniciales','initial_liability':'VPA modelado',
        'initial_coverage':'Cobertura inicial','initial_funding_gap':'Brecha actuarial inicial',
        'first_insufficiency_month':'Primer mes insuficiente','external_support_total':'Aportes externos nominales',
        'external_support_pv':'VPA aportes externos','required_support_pv':'VPA faltantes de caja',
        'unpaid_total':'Impagos nominales','terminal_pending':'Cola pendiente'}
    def table(frame,columns):
        return frame[[c for c in columns if c in frame]].rename(columns=labels).to_html(
            index=False,escape=True,float_format=lambda x:f'{x:,.3f}',na_rep='No definido/no observado')
    units='Unidades monetarias abstractas; no COP ni SMMLV vigente'
    row=base.loc[base.cohort.eq('A')]
    if len(row):
        a=row.iloc[0]
        finding=f"A: {int(a.participants)} registros; cobertura inicial {a.initial_coverage:.3f}; primer mes insuficiente {a.first_insufficiency_month}."
    else: finding='No se proporcionó resultado de cohorte A.'
    descriptions={
        '01_isc':('Segmentos ISC','Universo aplicable y calculable','Registros','Intervalos excluyentes; denominador indicado en la figura.'),
        '02_capital_obligaciones':('Activos y obligaciones','Cohortes exploratorias A–E y adicional',units,'El requerimiento fuente no es el pasivo modelado.'),
        '03_cobertura':('Cobertura actuarial inicial','Mismas cohortes y supuestos','Capital / VPA','No es indicador regulatorio ni selección óptima.'),
        '04_activos':('Trayectoria de activos','Cohorte A, sin respaldo',units,'Activos al cierre; no se suman ingresos por fallecimiento.'),
        '05_prestaciones':('Prestaciones debidas y financiadas','Cohorte A, sin respaldo',units+'/mes','Devengo al inicio, desembolso al cierre de mes.'),
        '06_respaldo':('Aportes externos acumulados','Cohorte A, garantía hipotética frente a sin respaldo',units,'No son reserva actuarial ni capital inicial requerido.'),
        '07_sensibilidad':('Sensibilidad determinística','Cohorte A, garantía hipotética',units+' descontadas','Una variable por vez; no representa probabilidad de insuficiencia.')}
    def image(key):
        if key not in figures: return ''
        title,population,unit,note=descriptions[key]
        svg=base64.b64encode(Path(figures[key]).read_bytes()).decode('ascii')
        return '<figure><h3>'+html.escape(title)+'</h3><img alt="'+html.escape(title)+'" src="data:image/svg+xml;base64,'+svg+'"><figcaption><p>Población: '+html.escape(population)+'. Unidad: '+html.escape(unit)+'.</p><p>Lectura descriptiva: '+html.escape(finding)+'</p><p>'+html.escape(note)+'</p></figcaption></figure>'
    universe=analysis['universe']
    adaptation=analysis.get('adaptation')
    diagnosis=table(adaptation,['state','records']) if adaptation is not None else '<p>Entrada sintética de fase 2; no presupone validación de una base institucional.</p>'
    sections=[
        ('1. Resumen de la población','<p>Ejercicio sintético, sin datos institucionales. Las cohortes acumulativas se superponen y no se suman.</p>'+table(universe,['grupo','registros'])),
        ('2. Calidad y adaptación de datos',diagnosis+'<p>'+html.escape(str(analysis['quality']))+'</p>'),
        ('3. Segmentación ISC','<p>ISC = (capital + bono) / requerimiento fuente para 1 SM. Catálogo único y desconocidos pendientes; capital negativo no clasifica.</p>'+table(universe,['grupo','registros'])+'<p>A&lt;1; B&lt;1,05; C&lt;1,10; D&lt;1,15; E&lt;1,20. Adicional: [1;1,20). No determinan elegibilidad ni predicen descapitalización.</p>'+image('01_isc')),
        ('4. Valoración actuarial','<p>RAC individual = capital / VPA propio; no equivale al ISC. Cobertura agregada = suma capital / suma VPA. Cero VPA deja cociente no definido.</p>'+image('02_capital_obligaciones')+image('03_cobertura')),
        ('5. Sostenibilidad de la bolsa','<p>Régimen de referencia: sin respaldo externo. Garantía hipotética en figura separada; prestaciones variables no equivalen a garantía vitalicia.</p>'+image('04_activos')+image('05_prestaciones')+image('06_respaldo')),
        ('6. Comparación de cohortes','<p>Una fila por cohorte. Régimen de referencia explícito: sin respaldo externo (no_support).</p>'+table(base,['cohort','participants','initial_capital','initial_liability','initial_coverage','first_insufficiency_month','terminal_pending'])),
        ('7. Sensibilidades',image('07_sensibilidad')+'<p>Se varía mortalidad, rentabilidad, indexación, gastos o descuento por separado. Permanecen fijos población, prestación inicial y horizonte; las demás tasas no se acoplan.</p>'),
        ('8. Limitaciones y pendientes','<p>'+html.escape(LIMITATIONS)+'</p><p>Calibrar mortalidad, caracterizar beneficiarios, validar unidad persona/catálogo y valorar la cola antes de una conclusión actuarial.</p>')]
    if technical:
        columns=['cohort','regime','participants','initial_capital','initial_liability','initial_funding_gap',
            'initial_coverage','first_insufficiency_month','external_support_total','external_support_pv',
            'required_support_pv','unpaid_total','terminal_pending']
        definitions=''.join('<dt>'+html.escape(k)+'</dt><dd>'+html.escape(v)+'</dd>' for k,v in METRICS.items())
        sections.append(('Anexo técnico: regímenes, conceptos y escenarios','<dl>'+definitions+'</dl>'+table(summary,columns)+
            table(analysis['sensitivity'],['scenario']+columns)+'<pre>'+html.escape(json.dumps(analysis['parameters'],ensure_ascii=False,indent=2))+'</pre>'))
    body=''.join('<section><h2>'+title+'</h2>'+content+'</section>' for title,content in sections)
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Integración actuarial — DATOS SINTÉTICOS</title><style>body{background:white;color:#0033A0;font-family:Arial,sans-serif;max-width:1200px;margin:auto;padding:24px}p{line-height:1.6}section{margin:40px 0;overflow-x:auto}figure{margin:28px 0}figcaption{font-size:14px;color:#0033A0}img{width:100%;height:auto}table{border-collapse:collapse;font-size:13px}th,td{padding:10px;border-bottom:1px solid #4EC3E0;text-align:right}pre{white-space:pre-wrap}</style></head><body><h1>Integración actuarial — DATOS SINTÉTICOS</h1><p>Sin resultados observados de Protección ni afirmación de viabilidad.</p>'+body+'</body></html>'


def write_integrated_reports(analysis,figures,output):
    output=Path(output)
    (output/'executive.html').write_text(report_html(analysis,figures),encoding='utf-8')
    (output/'technical/report.html').write_text(report_html(analysis,figures,True),encoding='utf-8')


def validated_report(simulation,policy):
    """HTML local agregado, protegido como un paquete único contra diferencias."""
    from src.utils.disclosure import disclosure_decision
    from src.actuarial.eligibility import build_isc_cohorts
    d=simulation.diagnosis
    # Recuento de máscaras, sin resolver duplicados eliminando registros.
    frame=d.adapted.frame
    cohorts={name:int((frame.isc_aplicable & frame.ISC.lt(t)).sum()) for name,t in zip('ABCDE',(1,1.05,1.1,1.15,1.2))}
    counts=list(d.by_state.records)+list(d.by_cause.records)+list(d.isc_reconciliation.records)
    counts+=list(simulation.reconciliation[['selected','ready','pending','valued','simulated']].iloc[0])
    allowed,note=disclosure_decision(len(frame),counts,cohorts,policy)
    if not allowed:
        return '<html lang="es"><meta charset="utf-8"><p>'+html.escape(note)+'</p></html>'
    # Solo campos autorizados, sin etiquetas de catálogo ni metadatos arbitrarios.
    content=d.by_state.to_html(index=False,escape=True)+simulation.reconciliation.to_html(index=False,escape=True)
    return '<html lang="es"><meta charset="utf-8"><h1>Diagnóstico local autorizado</h1>'+content+'<p>'+html.escape(note)+'</p></html>'
