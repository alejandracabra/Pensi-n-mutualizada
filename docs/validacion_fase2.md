# Validación de fase 2 — 5 de noviembre de 2026

Todos los valores siguientes provienen exclusivamente del generador sintético. No son datos ni resultados de Protección y no demuestran viabilidad.

## Pruebas y ejecución

- 57 pruebas aprobadas: 29 preexistentes y 28 nuevas, incluidas exportación integral y pruebas de privacidad con datos canario.
- `python -m unittest discover -s tests -v`: OK (33,948 s en la comprobación final).
- `python -m src.simulation.integrated`: generación completa de HTML técnico y ejecutivo, siete PNG y siete SVG, tablas agregadas y parámetros.
- Sin modificación de notebooks históricos; sin commits, push ni cambios en main.
- `git diff --check` sin errores; salidas verificadas como excluidas de Git.

## Entorno comprobado

Python 3.10.9; numpy 1.23.5, pandas 1.5.3, matplotlib 3.7.0, plotly 5.9.0.

Se usó el entorno Anaconda disponible. Sus versiones son anteriores a las mínimas declaradas en requirements.txt (incluido Python 3.11+): las pruebas no certifican ese entorno objetivo ni una instalación limpia. Las versiones exactas y hashes del código están en el manifiesto de cada ejecución; la validación en un entorno limpio de Python 3.11+ sigue pendiente.

## Demostración base: garantía hipotética

Descuento 3%, rendimiento 2%, indexación 2%, gastos 3% de prestaciones; tabla sintética y ausencia de beneficiarios como hipótesis explícita. Horizonte común de 600 meses.

| Cohorte | Registros | Capital inicial | VPA modelado | Cobertura | Primer mes insuficiente | VPA aportes externos |
|---|---:|---:|---:|---:|---:|---:|
| A | 12 | 1182.600 | 3064.380 | 0.386 | 102 | 1928.775 |
| B | 18 | 2276.100 | 4771.750 | 0.477 | 133 | 2611.626 |
| C | 24 | 3423.600 | 6052.743 | 0.566 | 155 | 2827.830 |
| D | 30 | 4625.100 | 7807.432 | 0.592 | 167 | 3471.569 |
| E | 36 | 5880.600 | 9318.221 | 0.631 | 180 | 3828.722 |
| adicional | 24 | 4698.000 | 6253.840 | 0.751 | 224 | 1933.716 |

Los capitales y VPA son unidades abstractas. Las cohortes A–E se superponen: no se suman sus registros, activos, pasivos ni aportes. El grupo adicional es E menos A. Todas tienen cola pendiente en esta ejecución.

En A, el primer faltante ocurre en el mes 102. Sin garantía se acumulan prestaciones y gastos no financiados; con garantía se aportan recursos externos hipotéticos. Su cobertura de aproximadamente 0,386 compara capital con VPA truncado y no permite inferir viabilidad vitalicia. La mutualización no elimina esa brecha.

## Cambios y límites

Se modificaron README.md, docs/piloto_mutualizacion.md, docs/proyecto.md, eligibility.py y pool.py. Se añadieron liabilities.py, programmed_withdrawal.py, simulation/integrated.py, visualization/integrated.py, utils/integrated_reporting.py, tests/test_integration.py, docs/integracion_actuarial.md y este registro.

La [metodología](integracion_actuarial.md) detalla fórmulas, estados de supervivencia, beneficiario independiente configurable, devengo/pago, garantía hipotética, registro de impagos y reserva truncada. Las próximas validaciones prioritarias son catálogo de riesgos y unidad persona, mortalidad y beneficiarios, reglas institucionales de prestaciones/gastos/retiro programado, cola vitalicia y evaluación jurídica.
