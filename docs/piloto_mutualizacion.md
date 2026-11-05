# Piloto determinístico sintético

## Alcance y supuestos

Este ejercicio prueba mecánica financiera; no evalúa viabilidad de Protección. Todas las cifras por defecto son ficticias, en unidades monetarias abstractas, y están etiquetadas como sintéticas. No lee Excel ni selecciona pensionados reales.

- Demografía: bolsa cerrada de 100 personas de edad 65, sin nuevas entradas ni retiros.
- Finanzas: capital inicial de 100 unidades por persona, rendimiento anual efectivo de 2%, gastos de 0,5% sobre activos después del rendimiento e indexación de 2%.
- Actuaría: pago anual inicial de 8 unidades por superviviente al cierre y secuencia ilustrativa de probabilidades anuales de muerte de 2% durante 30 años. No son parámetros estimados, tablas calibradas ni cifras institucionales.
- El número esperado de supervivientes puede ser fraccionario. No es una simulación de personas ni modela volatilidad.
- No hay retiros de saldos por muerte; el remanente ya está en el activo colectivo. La mortalidad reduce pagos futuros, no genera ingresos adicionales.

## Orden y conciliación

Para cada año: rendimiento sobre activo inicial, muertes esperadas, gastos sobre activos rentabilizados y pago anual al cierre a quienes sobreviven. La indexación comienza en el segundo pago.

`N_cierre = N_inicio * (1 - q)`

`A_cierre = A_inicio + rendimiento - pagos_efectivos - gastos_efectivos`

Si el activo disponible no cubre la demanda conjunta, se prorratean gastos y prestaciones. Se informa cada impago; no se permite saldo negativo ni financiación implícita. Los impagos no se capitalizan ni acumulan como deuda: el piloto no define derechos contractuales. Se continúa la proyección después de agotarse los activos para mostrar demanda no atendida. Saldo final positivo tampoco prueba suficiencia: pueden quedar supervivientes y obligaciones después del horizonte.

## ISC

Se conserva ISC = capital más bono / capital necesario para 1 SM y la clasificación estricta ISC < 1. Se conservan exclusiones GPM y Sustitución-GPM; un riesgo faltante no es aplicable bajo la implementación actual. Los riesgos desconocidos y capitales negativos requieren revisión de calidad: no se cambian automáticamente las reglas heredadas. La partición `isc_universe_summary` distingue no aplicables, aplicables no calculables, descapitalizados y no descapitalizados. El denominador debe declararse siempre.

Los umbrales 1,00; 1,05; 1,10; 1,15; 1,20 definen grupos acumulados anidados. Los rangos [1; 1,20) no se reclasifican como descapitalizados. No se optimiza selección para obtener resultados favorables. La suma del capital requerido individual de la fuente no es un pasivo calculado para la bolsa.

## Limitaciones y pendientes

No hay tablas de mortalidad calibradas, mejoras de longevidad, diferenciación por edad/sexo, ni información individual de beneficiarios. No se modelan sobrevivencia de cónyuges, sustituciones, garantías, herencias, impuestos, estructura real de gastos, inversión, riesgo de mercado o selección adversa. La ausencia de beneficiarios puede subestimar materialmente las obligaciones. Se requiere valorar esos derechos, validar exposición/mortalidad y documentar reglas antes de cualquier conclusión actuarial. Este piloto no afirma viabilidad ni constituye recomendación de producto.

## Ejecución reproducible

Desde la raíz, con Python 3.11+ y requirements.txt instalados:

```powershell
python -m unittest discover -s tests -v
python -m src.simulation.pilot
```

El piloto guarda parámetros, flujos y reporte técnico en `reports/outputs/piloto_sintetico/technical/`, y PNG/SVG 16:9 para PowerPoint en `reports/outputs/piloto_sintetico/powerpoint/`. Cada gráfica muestra un concepto y lleva la etiqueta DATOS SINTÉTICOS. Los resultados están excluidos de Git. Los generadores originales se conservan; no se ejecutan con datos corporativos en este bloque.

El inventario inicial está en `docs/revision_inicial.md`. No se modifican notebooks históricos ni sus resultados, no se hacen commits y no se publica nada.
