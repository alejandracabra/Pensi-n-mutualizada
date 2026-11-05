"""Reportes de agregados: nunca serializa participantes ni valores individuales."""
from pathlib import Path
import base64
import html

LIMITATIONS = (
    'Solo datos sintéticos; no son resultados observados de Protección. '
    'Mortalidad no calibrada y sin beneficiarios individuales en la demostración. '
    'VPA y reservas truncados al horizonte; si quedan supervivientes, existe valoración terminal pendiente. '
    'La cobertura inicial no es un índice de solvencia regulatorio. '
    'Garantía hipotética, sin atribuir su financiación ni autorización a Protección. '
    'No se modelan incertidumbre, selección voluntaria, dependencia, inversión ni reglas reales de retiro programado.'
)


def report_html(analysis: dict, figures: dict[str,Path], technical: bool = False) -> str:
    """Solo columnas agregadas permitidas; ignora detalle/metadata no declarados."""
    summary=analysis['comparison']
    allowed=['cohort','regime','participants','initial_capital','initial_liability','initial_coverage',
        'first_insufficiency_month','external_support_total','external_support_pv','unpaid_total','terminal_pending']
    labels={'cohort':'Cohorte','regime':'Régimen','participants':'Registros','initial_capital':'Capital',
        'initial_liability':'VPA modelado','initial_coverage':'Cobertura inicial',
        'first_insufficiency_month':'Primer mes insuficiente','external_support_total':'Respaldo nominal',
        'external_support_pv':'VPA respaldo','unpaid_total':'Impagos nominales','terminal_pending':'Cola pendiente'}
    def table(frame,columns):
        return frame[columns].rename(columns=labels).to_html(index=False,escape=True,float_format=lambda x:f'{x:,.3f}',na_rep='No definido/no observado')
    def image(key):
        if key not in figures: return ''
        svg=base64.b64encode(Path(figures[key]).read_bytes()).decode('ascii')
        return f'<img alt="Gráfica agregada {key}" src="data:image/svg+xml;base64,{svg}">'
    universe=analysis['universe']
    base=summary.query("regime == 'no_support'")
    sections=[
        ('1. Resumen de población y calidad de datos',
         '<p>Universos exhaustivos sobre registros sintéticos. Las cohortes cuentan registros únicos, no una población institucional validada.</p>'+
         table(universe,['grupo','registros'])+'<p>Alertas agregadas: '+html.escape(str(analysis['quality']))+'</p>'),
        ('2. Caracterización financiera', '<p>Capital disponible y requerimiento individual fuente se expresan en unidades abstractas. El requerimiento fuente no se usa como pasivo de la bolsa.</p>'+table(base,['cohort','participants','initial_capital'])),
        ('3. Segmentación ISC', '<p>ISC = (capital + bono) / capital necesario para 1 SMMLV según la fuente. Se excluyen GPM y Sustitución-GPM; riesgos desconocidos quedan pendientes de catálogo. Capital negativo no clasifica.</p>'+
         '<h3>Universos</h3>'+table(universe,['grupo','registros'])+'<h3>Grupos exploratorios</h3><p>A &lt;1; B &lt;1,05; C &lt;1,10; D &lt;1,15; E &lt;1,20 son acumulativos y se superponen. Adicional [1;1,20) excluye A. No son elegibilidad ni una predicción de descapitalización. No se suman cohortes.</p>'+image('01_isc')),
        ('4. Valoración actuarial preliminar','<p>RAC individual = capital / VPA propio; es distinto del ISC. Aquí solo se muestra cobertura agregada = suma capital / suma VPA. Sin cociente si VPA=0. VPA incluye únicamente prestaciones y gastos configurados.</p>'+image('02_capital_obligaciones')+image('03_cobertura')),
        ('5. Proyección de la bolsa','<p>Cohorte A fijada por ISC&lt;1, sin selección por desempeño. Sin respaldo: faltantes explícitos; garantía: aporte externo hipotético. Variable: pagos ajustados a recursos, sin garantía vitalicia. Devengo al inicio y pago al cierre de mes.</p>'+image('04_activos')+image('05_prestaciones')+image('06_respaldo')),
        ('6. Comparación de cohortes', table(summary,allowed)+image('07_sensibilidad')+'<p>Sensibilidades de una variable por vez, con idéntica composición, descuento y horizonte; no se determina una cohorte óptima.</p>'),
        ('7. Limitaciones y próximos pasos','<p>'+html.escape(LIMITATIONS)+'</p><p>Validar catálogos y unidad persona, calibrar mortalidad, obtener beneficiarios y reglas de retiro programado, validar derechos y garantías, cuantificar la cola y someter el modelo a revisión actuarial y jurídica.</p>')]
    if technical:
        detail=table(analysis['sensitivity'],['scenario']+allowed)
        sections.append(('Anexo técnico: sensibilidades y parámetros',detail+'<pre>'+html.escape(__import__('json').dumps(analysis['parameters'],indent=2,ensure_ascii=False))+'</pre>'))
    body=''.join(f'<section><h2>{title}</h2>{content}</section>' for title,content in sections)
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Integración actuarial — DATOS SINTÉTICOS</title><style>body{background:white;color:#0033A0;font-family:Arial,sans-serif;max-width:1200px;margin:auto;padding:24px}p{line-height:1.6}section{margin:32px 0;overflow-x:auto}img{width:100%;height:auto}table{border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid #4EC3E0;text-align:right}pre{white-space:pre-wrap}.notice{border-left:5px solid #FFE946;padding:16px}</style></head><body><h1>Integración actuarial — DATOS SINTÉTICOS</h1><p class="notice">Ejercicio académico en unidades abstractas. No contiene resultados de Protección ni demuestra viabilidad.</p>'+body+'</body></html>'


def write_integrated_reports(analysis: dict, figures: dict, output: Path) -> None:
    output=Path(output)
    (output/'executive.html').write_text(report_html(analysis,figures),encoding='utf-8')
    (output/'technical/report.html').write_text(report_html(analysis,figures,technical=True),encoding='utf-8')
