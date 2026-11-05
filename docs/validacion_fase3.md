# Validación fase 3 — 5 de noviembre de 2026

## Alcance verificado

Rama `refactor/piloto-mutualizacion`, commit base `91ca27d`. Los cambios de fase 3 permanecen locales, sin commit, push ni merge. Solo se utilizaron datos sintéticos. No se solicitaron ni leyeron bases corporativas; no se modificaron notebooks ni datos/resultados históricos.

## Correcciones de auditoría

| Aspecto | Corrección comprobada |
|---|---|
| Catálogo/universos | Objeto único configurable, aliases explícitos, exclusiones obligatorias, desconocidos/faltantes y herencia consistente del catálogo en consumidores ISC. Cambios de criterio requieren reclasificación explícita. |
| Adaptación y preparación | Esquema/configuración separados; lectura binaria de solo lectura, identificación sin deduplicación, validación por causa y estado; cohorte incompleta bloqueada y parcial con opt-in/advertencia. |
| Interpretación del respaldo | Activos, VPA, brecha inicial, reserva futura, faltantes de caja, aportes y VPA de aportes separados. Pruebas demuestran que no son intercambiables. |
| Mortalidad/beneficiarios/cola | Tabla suministrada en memoria con período, metadatos y cobertura; estados explícitos de beneficiarios; supervivencia residual y cola no valorada representada como NaN, no cero. |
| Descuento y rendimiento | Parámetros independientes, sensibilidad de descuento añadida; mismas entradas reproducen flujos y cambiar rendimiento no cambia el VPA si descuento permanece fijo. |
| Ejecutivo | Ocho secciones, seis filas de comparación bajo régimen sin respaldo; regímenes y escenarios completos en técnico, con población/unidades/lectura/notas de cada figura. |

## Pruebas

`python -m unittest discover -s tests -v`: **94 pruebas aprobadas** en 39,205 segundos: 57 preexistentes + 37 nuevas. Ninguna prueba histórica se eliminó ni cambió. La batería nueva cubre:

- Catálogo, aliases, exclusiones, configuración, conciliación y gráficas con categorías personalizadas.
- Campos ausentes, mapeos alternativos, colisiones, capitales no numéricos/negativos/infinitos, identificación duplicada, edad/sexo y unidad de observación.
- Escenarios de prestación, fecha/vigencia, moneda y escalado explícito.
- Hash del archivo Excel original idéntico antes/después, cierre de handles en Windows y rechazo de cabeceras duplicadas.
- Causas superpuestas, partición principal exhaustiva, bloqueo por defecto, parcial explícita y revalidación tras mutar datos.
- Beneficiario informado que genera pagos después del fallecimiento del titular, estados familiares faltantes/incompatibles y estructuras contradictorias.
- Mortalidad por período/vigencia y ausencia de extrapolación; descuento/rendimiento independientes, brecha frente a aportes y cola pendiente.
- Celdas pequeñas, complementos y diferencias entre cohortes; bloqueo de salidas no sintéticas, ausencia de valores canario e identificación en reportes.
- Ejecutivo con seis cohortes y técnico con los tres regímenes completos.

En pruebas nuevas se corrigió una fuga de handle de Excel en Windows: el lector ahora cierra el archivo fuente antes de procesar el contenido en memoria. También se precisaron dos oráculos de pruebas nuevas: el encabezado de Pandas es `<tr style=...>` y una tabla de edades 65/66 para dos períodos sí cubre 24 meses, pero no un horizonte de 36. Los resultados actuariales no se alteraron para satisfacer esas comprobaciones.

## Conciliación de la demostración de adaptación

Todos los números siguientes son ficticios y proceden de `synthetic_incomplete_source()`. No son cifras observadas de Protección ni una valoración de su población.

| Etapa/indicador | Registros |
|---|---:|
| Leídos | 16 |
| Mínimo estructural/tipos para ISC | 14 |
| No aplicables por regla | 1 |
| Riesgo desconocido | 1 |
| Riesgo faltante | 0 |
| Aplicables | 14 |
| ISC calculable en toda la base | 14 |
| Aplicables con ISC calculable | 12 |
| Aplicables sin ISC calculable | 2 |
| ISC<1 aplicables | 12 |
| ISC>=1 aplicables | 0 |
| Cohortes A/B/C/D/E, cada una por separado | 12 |
| Grupo adicional | 0 |
| Preparados para valoración | 3 |
| Pendientes de identificación | 2 |
| Pendientes de riesgos | 1 |
| Alguna dependencia actuarial pendiente | 7 |
| Seleccionados A | 12 |
| Pendientes dentro de A | 9 |
| Valorados en ejecución parcial explícita | 3 |
| Simulados | 3 |

Las tasas de exclusión usan siempre el denominador seleccionado: 9/12 = **75%** en A. Esta subpoblación no se presume representativa. Las cohortes se superponen; no se suman. Los indicadores jerárquicos y causas tampoco constituyen particiones sumables.

El estado principal distribuye las 16 filas en 3 preparadas, 2 con identificación pendiente y una en cada estado restante: edad, sexo, beneficiarios, capital, prestación, riesgo excluido, riesgo pendiente, ISC no calculable, fecha, mortalidad y moneda. Sus cantidades suman 16. Los problemas simultáneos permanecen en `causes`.

La ejecución normal se bloquea. La demo declara explícitamente `allow_partial=True`, emite advertencia y forma una bolsa de 3 participantes con 120 unidades abstractas (3 × 40). Se concilian los pasivos con los valores individuales y las identidades financieras; el mismo conjunto valorado ingresa en la simulación. No se asignan a la bolsa capitales de las filas pendientes.

## Artefactos y privacidad

Se generó un directorio nuevo `reports/outputs/fase3_sintetica/` con `diagnosis.html`, tablas agregadas, transformaciones y flujos A. En `model/` se generaron ejecutivo/técnico y siete PNG/SVG del ejemplo sintético financiero de fase 2 actualizado. **Son dos demostraciones distintas**: la primera ilustra adaptación de 16 filas incompletas; la segunda conserva las cohortes sintéticas financieras anteriores. Sus poblaciones no se mezclan ni se presentan como una misma base.

Los resultados generados y configuraciones locales están excluidos de Git. No se exportan DataFrames individuales ni IDs/nombres de la fuente. La API de adaptación/simulación permanece en memoria y la divulgación no sintética está denegada por defecto. Una revisión de umbrales no basta para certificar anonimato ni autorizar publicación: se requiere revisión contextual de todas las tablas, gráficas y otras salidas disponibles.

`git diff --check` sin errores. El último commit sigue siendo `91ca27d`: no se publicó esta fase.

## Archivos

Creados: `src/data/risk_catalog.py`, `schema.py`, `adapter.py`, `validation.py`, `mortality.py`; `src/simulation/validated.py`, `adaptation_demo.py`; `src/utils/disclosure.py`; los dos ejemplos YAML; `tests/test_data_adapter.py`; `docs/adaptacion_datos.md` y este registro.

Modificados: `.gitignore`, `requirements.txt`, `README.md`, `docs/integracion_actuarial.md`, `src/actuarial/eligibility.py`, `pool.py`, `src/data/loader.py`, `src/simulation/integrated.py`, `src/utils/integrated_reporting.py`, `src/visualization/integrated.py`.

## Ejecución y límites del entorno

```powershell
python -m unittest discover -s tests -v
python -m src.simulation.adaptation_demo
```

La demo rechaza un directorio ya existente. Para repetirla sin sobrescribir historial, usar `generate_demo` con una nueva subcarpeta de `reports/outputs`.

Se comprobó en Anaconda Python 3.10.9, numpy 1.23.5, pandas 1.5.3, matplotlib 3.7.0, plotly 5.9.0 y PyYAML 6.0. Estas versiones son anteriores a las mínimas declaradas para varios paquetes/Python: sigue pendiente certificar una instalación limpia de Python 3.11+ con requirements.txt. No se instaló otro entorno ni se cambió el entorno existente.

## Dependencias aún pendientes para una base real

Validar autorización/entorno local, unidad de análisis, categorías/versiones, fechas/precios/escalas, prestación objetivo suministrada, beneficiarios, tablas y mejoramientos, gastos/indexación/descuento/inversión y derechos contractuales. Las referencias históricas de universos deben contrastarse después con la base autorizada: no se han comprobado ni forzado en esta fase. Deben calibrarse mortalidad y cola vitalicia y revisarse las reglas reales de retiro programado y el marco jurídico/regulatorio antes de interpretar viabilidad. No se implementó Monte Carlo.
