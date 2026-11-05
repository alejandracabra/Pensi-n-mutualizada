# Integración actuarial y financiera — fase 2

## Alcance y estado

Se implementan selección ISC, valoración individual, formación de bolsa y proyección mensual con datos sintéticos compatibles con las columnas de la base. Se conserva la API anual de la primera fase como referencia histórica; la fase 2 usa exclusivamente el modelo mensual heterogéneo. No se modifican notebooks históricos, datos originales ni resultados existentes. No se hacen commits ni push.

La participación voluntaria y la administración/asunción interna de obligaciones sin aseguradora son hipótesis de diseño, pendientes de evaluación jurídica, regulatoria y actuarial. El código no acredita autorización ni viabilidad de un producto.

```mermaid
flowchart LR
  A[Selección ISC y calidad] --> B[Valoración actuarial individual]
  B --> C[Formación de la bolsa: F0 y L0]
  C --> D[Proyección mensual de flujos]
  D --> E[Evaluación de faltantes y sensibilidades]
```

## Módulos y compatibilidad

| Archivo | Función |
|---|---|
| `src/actuarial/eligibility.py` | Normalización de riesgos, alertas, clasificación, cohortes y estadísticas. Conserva nombres y columnas del EDA. |
| `src/actuarial/liabilities.py` | Tabla configurable edad/sexo/período, conversión mensual, derechos esperados, VPA y RAC; beneficiario opcional explícito. |
| `src/actuarial/pool.py` | `value_cohort` y `project_monthly_pool`; conciliación de valoración y flujos. Conserva `project_pool` anual. |
| `src/actuarial/programmed_withdrawal.py` | Protocolo y requisitos de retiro programado; ejecución deliberadamente pendiente. |
| `src/simulation/integrated.py` | Datos sintéticos determinísticos, comparación de cohortes, escenarios y trazabilidad de ejecución. |
| `src/visualization/integrated.py` | Siete figuras SURA, un concepto por figura, PNG 300 dpi y SVG 16:9. |
| `src/utils/integrated_reporting.py` | HTML ejecutivo y técnico autónomos con tablas agregadas y figuras embebidas. |
| `tests/test_integration.py` | Casos actuariales analíticos, conciliación financiera, cohortes, sensibilidad, exportación y privacidad. |

Los generadores EDA y ejecutivos anteriores mantienen sus interfaces. El reporte de fase 2 es independiente: no mezcla una simulación con resultados observados ni reemplaza el dashboard histórico.

## ISC y selección

`ISC_i = capital_mas_bono_i / capital_necesario_sm_i` conserva su definición. El capital requerido fuente no se usa para valorar las obligaciones de la nueva bolsa.

Se normalizan tildes, espacios y guiones de riesgos. GPM y SUSTITUCIÓN-GPM permanecen excluidos, incluso si aparecen en un catálogo personalizado. El catálogo por defecto VEJEZ/INVALIDEZ/SOBREVIVENCIA/SUSTITUCION es operativo y provisional, no una certificación de categorías institucionales. Riesgos desconocidos o faltantes quedan fuera del universo aplicable hasta validación; se cuentan en alertas. Se puede proporcionar `known_risks` explícitamente al clasificador y constructor de cohortes. Las comparaciones integradas usan el catálogo provisional por defecto.

El capital negativo genera alerta; `ISC_bruto` conserva el cociente diagnóstico, pero `ISC` y la clasificación quedan nulos. Capital faltante/no numérico/no finito, denominador no positivo/inválido y edad inválida tienen alertas separadas. La edad inválida no altera el cociente: impide la posterior valoración, que exige edad válida. La concordancia de clasificación compara solo registros aplicables, calculables y con importe fuente válido; un dato fuente faltante no se interpreta como cero. La concordancia de importes es un diagnóstico algebraico de valores exportados, no una validación de cálculos actuariales externos.

La partición exhaustiva separa no aplicables, aplicables sin ISC calculable, ISC<1 y ISC>=1. El conteo calculable en toda la base es distinto del calculable dentro del universo aplicable; ambos se informan. No se muestran porcentajes sobre denominadores mezclados.

A: ISC<1; B: ISC<1,05; C: ISC<1,10; D: ISC<1,15; E: ISC<1,20. Son acumulativas y anidadas; **no deben sumarse**. Adicional: 1<=ISC<1,20, excluyente respecto A; A unión adicional = E. Son grupos exploratorios, no elegibilidad, cercanía temporal a descapitalización, selección óptima ni predicciones. Cada cohorte se resume por registros, edad y capitales: cantidad, media, mediana, mínimo, máximo y suma donde corresponde.

`registro` debe ser único y no nulo para formar cohortes/proyectar. Sin registro, el selector admite índice único, pero el valorador exige un identificador explícito. No se deduplica automáticamente ni se eliminan duplicados por conveniencia: debe resolverse la unidad persona/registro con el dueño de los datos.

## Mortalidad y temporalidad

La tabla admite q anual por edad cumplida y sexo; `*` representa una hipótesis unisex explícita. Factores por año de valoración permiten cambios de período. Una edad o período no cubierto genera error; no se extrapola silenciosamente. Se usa:

`q_m = 1 - (1 - q_anual)^(1/12)`

Así se conserva la supervivencia anual bajo fuerza constante dentro de cada tramo anual. Se consulta la edad cumplida de inicio de cada mes y el año desde valoración. La curva de demostración es `min(0.95, multiplicador * 0.004 * exp(0.075*(edad-60)))` para edades 0–150. Es una construcción matemática sintética: no es RV08, RV09 ni experiencia de Protección; tampoco representa una estimación colombiana.

Con `S_0=1`, `S_m=S_(m-1)*(1-q_m)`. El derecho mensual completo se devenga al inicio si el pensionado está vivo y se paga al cierre: `P_m = b_0*(1+g)^((m-1)/12)*S_(m-1)`. Por ello, incluso con mortalidad total durante el primer mes, se conserva el primer pago devengado. No se modela prorrata diaria ni pagos extraordinarios adicionales. La indexación es crecimiento compuesto mensual derivado de una tasa anual efectiva constante, no una regla institucional de actualización del SMMLV.

## Beneficiarios

El ejemplo principal declara una **hipótesis sin beneficiarios**; la falta de datos no prueba su ausencia. La interfaz acepta un único beneficiario con edad, sexo, tabla y fracción explícitos. Bajo independencia de vidas, el pago esperado post muerte del titular es:

`P_b,m = b_m * fracción * (1-S_titular,m-1) * S_beneficiario,m-1`.

El beneficiario recibe desde el inicio del mes posterior al fallecimiento, sin duplicar el derecho ya devengado del titular. La fracción no tiene valor legal por defecto. Las pruebas incluyen continuidad de pagos después de la muerte del titular. No se incluyen grupos múltiples, hijos con vencimiento, dependencia entre vidas, orden de prelación o sustituciones reales: requieren otro modelo de estados y reglas validadas.

## Valor presente y respaldo

`G_m = fracción_gasto * (P_m + P_b,m) + gasto_fijo * receptores_esperados_m`.

Los gastos son por prestación/receptor, no una comisión sobre activos. En el caso de beneficiario, receptores esperados = supervivencia del titular + probabilidad de beneficiario vivo con titular fallecido.

`VPA_i = suma_m (P_i,m + G_i,m) / (1+d)^(m/12)`.

`RAC_i = capital_i / VPA_i`; VPA cero produce NaN, nunca infinito. Es distinto del ISC. Se conserva el detalle individual en memoria para auditoría, pero no se exporta a los reportes.

`F0 = suma_i capital_i`, `L0 = suma_i VPA_i`, `cobertura_inicial = F0/L0` (NaN si L0=0). Solo incluye los gastos y prestaciones expresamente modelados; no es un indicador regulatorio ni certifica solvencia. La brecha inicial `max(L0-F0,0)` es distinta de los aportes de caja que surgen durante la trayectoria financiera.

## Formación y proyección de la bolsa

Se valora cada participante con su edad, sexo, capital y prestación. La cohorte comparte horizonte, descuento, gastos e indexación. Para comparar cohortes se fija un horizonte común: hasta que el participante más joven de E alcance la edad terminal configurada (110 en la demostración). Los mayores siguen proyectados en ese horizonte; no se eliminan al llegar a 110. Se puede fijar `horizon_months` explícitamente. Con beneficiarios, la valoración de una cohorte puede extenderse hasta la edad terminal de la vida más joven.

La conversión de rentabilidad es `r_m=(1+r_anual)^(1/12)-1`. Cada mes: rendimiento sobre activo inicial, obligaciones debidas del valorador, pago/gasto y aporte externo si corresponde.

`F_m = F_(m-1) + rendimiento_m + aporte_externo_m - prestaciones_pagadas_m - gastos_pagados_m`.

Tres regímenes sobre los mismos derechos de referencia:

- **Sin respaldo:** la bolsa no toma deuda ni recibe aportes; si no alcanza, prorratea prestaciones y gastos. Se registra lo debido, lo financiado, cada impago y su acumulado nominal. Esta trayectoria no cumple una promesa garantizada cuando hay faltantes.
- **Garantía hipotética:** `aporte=max(prestaciones_debidas+gastos_debidos-activos_disponibles,0)`. Se mantienen todos los pagos debidos y se separa lo pagado por la bolsa del componente financiado externamente. No se atribuye ese aporte a Protección en la práctica.
- **Prestaciones variables:** misma mecánica de ajuste a recursos, identificada como reducción respecto de una prestación objetivo. `benefit_due` funciona aquí como referencia objetivo del escenario fijo, no como certificación de una promesa contractual variable ni como garantía vitalicia. Los faltantes de esa referencia se conservan para comparabilidad.

Los impagos sin respaldo se registran como obligaciones pendientes nominales, sin intereses y sin volver a pagarlos automáticamente en períodos siguientes. No desaparecen del registro acumulado. Es una convención contable exploratoria; una regla contractual de mora/recuperación necesitaría ampliación. El respaldo requerido de caja por mes, su total y su valor presente se distinguen del respaldo efectivamente inyectado (cero sin garantía).

La reserva futura mensual corresponde al VPA, al cierre de ese mes, de flujos posteriores dentro del horizonte. Una recursión retrospectiva concilia la reserva inicial con L0. `pending_obligations` suma esa reserva e impagos nominales acumulados: no es un pasivo regulatorio. `future_reserve_gap` compara la reserva futura truncada con activos; no incorpora obligaciones posteriores al horizonte.

No se retiran capitales al fallecer ni se suman ingresos ficticios por mortalidad: los recursos ya están en la bolsa. No hay nuevas adhesiones, aportes regulares, herencias o transferencias en esta versión.

## Horizonte y cola pendiente

La edad terminal es un límite de proyección, no una edad cierta de muerte. Si quedan supervivientes del titular o potenciales beneficiarios con derechos, `terminal_pending=True`. No se asigna una cola de valor cero: su valoración permanece pendiente, fuera del VPA informado. Una cobertura elevada o activos finales positivos no demuestra suficiencia vitalicia.

## Escenarios reproducibles

El generador crea 42 registros sintéticos regulares con edades 60–84, sexos alternos, prestación mensual de 1 unidad abstracta, requerimiento fuente de 180 unidades e ISC predefinidos a ambos lados de los umbrales. Añade cinco casos de calidad/exclusión. No son importes COP ni un SMMLV vigente. Ninguna fila proviene de Protección.

Base: descuento anual 3%, rendimiento 2%, indexación 2%, gastos 3% de la prestación, cero gastos fijos, tabla sintética unisex. Se varía una hipótesis por vez: mortalidad por 0,7; rentabilidad -1%; indexación 4%; gastos 8%. Son cifras de demostración, no supuestos recomendados ni calibrados. Se mantiene la misma población y horizonte entre escenarios. Se evalúan las seis cohortes en los tres regímenes; no se optimiza ni se modifica selección por resultados.

## Ejecución y exportaciones

Desde la raíz, con el entorno y requirements.txt instalados:

```powershell
python -m unittest discover -s tests -v
python -m src.simulation.integrated
```

En esta máquina puede usarse el intérprete existente:

```powershell
& 'C:\Users\macab\anaconda3\python.exe' -m src.simulation.integrated
```

Todo se guarda en `reports/outputs/integracion_sintetica/` (excluido de Git):

- `executive.html`: las siete secciones solicitadas, sin microdatos.
- `technical/report.html`: anexo de sensibilidades y supuestos, autónomo sin CDN.
- `powerpoint/`: siete PNG 4000×2250 y sus SVG; una figura por concepto.
- `technical/`: comparación, sensibilidad, universos, estadísticas de cohortes, calidad, parámetros y 18 tablas de flujos agregados mensuales.

`parameters.json` registra hipótesis, fórmula sintética, versión de Python, bibliotecas, commit base y SHA256 de cada módulo ejecutado. Esto identifica cambios locales aun sin crear commits. No se exportan identificadores, nombres, capitales individuales ni RAC individuales. Las pruebas de privacidad usan valores canario y campos extra para comprobar su ausencia en HTML, CSV, JSON y SVG.

## Uso posterior con datos reales y próximos pasos

Antes de utilizar datos reales se necesita autorización y un entorno aprobado, definición de unidad persona, diccionario y catálogo de riesgos validado, fecha y moneda de valoración, edades fiables, capitales verificables, beneficiarios y reglas de sustitución, mortalidad calibrada y mejoras, reglas de gastos/indexación, garantías, inversión y derechos contractuales. El generador de fase 2 no acepta archivos corporativos ni descarga fuentes.

La interfaz de retiro programado lanza `NotImplementedError` hasta contar con fórmulas de recálculo, periodicidad, tabla/tasa técnica, beneficiarios, garantías, comisiones, rendimientos y reglas de agotamiento/fallecimiento. No se calcula una comparación falsa.

Permanecen pendientes calibración actuarial, dependencia y mejoras de mortalidad, múltiples beneficiarios, reglas institucionales de prestaciones y administración, cola vitalicia, incertidumbre, selección voluntaria/adversa y revisión jurídica/regulatoria. Primero validar esta estructura determinística y sus convenciones; Monte Carlo no se implementa todavía.
