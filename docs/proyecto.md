# Descripción del proyecto

## Planteamiento del problema

Algunos afiliados al sistema de ahorro individual en Colombia pueden llegar a la etapa de retiro con un capital que no alcanza a financiar una pensión por los mecanismos tradicionales. El proyecto estudia conceptualmente una modalidad colectiva en la que los participantes aportan el capital disponible a una bolsa mutualizada y reciben una mesada objetivo equivalente a un salario mínimo legal mensual vigente (SMMLV). Bajo el mecanismo planteado, el capital remanente de una persona fallecida permanece en la bolsa y contribuye a financiar las prestaciones de quienes sobreviven.

La pregunta central es bajo qué condiciones demográficas, financieras, operativas y de diseño este mecanismo podría sostener el pago de las prestaciones a lo largo del tiempo. La mutualización del riesgo de longevidad puede redistribuir recursos entre participantes, pero no elimina los riesgos de insuficiencia de capital, cambios en mortalidad, inflación, rentabilidad, selección adversa ni restricciones regulatorias.

## Objetivo general

Generar evidencia cuantitativa que permita determinar la viabilidad de una modalidad de pensión mutualizada para afiliados con cuentas de ahorro individual descapitalizadas, considerando la mutualización del riesgo de longevidad y la sostenibilidad financiera del esquema.

## Objetivos específicos

1. Caracterizar la población de afiliados descapitalizados.
2. Analizar la distribución de los capitales disponibles.
3. Estimar mortalidad y supervivencia.
4. Construir un modelo de bolsa mutualizada.
5. Evaluar la sostenibilidad bajo múltiples escenarios.
6. Identificar riesgos y condiciones de viabilidad.

## Datos disponibles y alcance

Se cuenta con un archivo de control de saldos con aproximadamente 94.000 registros. Entre las variables reportadas están riesgo, mesada, número de mesadas, capital, edad, sexo, estados, fechas de generación y siniestro, capitales necesarios para distintos objetivos y clasificaciones de descapitalización/desfinanciación, además de expectativa de vida.

El archivo de trabajo actual (`Base_Proyecto.xlsx`) se encuentra en la raíz local del proyecto y está excluido de Git. Los nombres, tipos, unidades, fechas de corte, definiciones de negocio, calidad y significado de sus variables deben confirmarse con el responsable de los datos antes de utilizarlos. No se deben publicar microdatos, identificadores ni resultados que permitan reidentificar personas.

El análisis está limitado inicialmente a una evaluación académica y determinística. No representa una recomendación de producto, una promesa de prestación ni una validación jurídica o regulatoria.

## Metodología preliminar

1. **Gobierno y perfilamiento de datos:** confirmar autorización, diccionario de datos, fecha de corte, granularidad, duplicados, faltantes, rangos, categorías y consistencia temporal. Definir reglas reproducibles y conservar inalterada la fuente original.
2. **Criterios de población:** acordar con expertos de negocio definiciones operativas de afiliado descapitalizado/desfinanciado y documentar exclusiones. Caracterizar la población por edad, sexo, capital y demás dimensiones permitidas.
3. **Preparación analítica:** normalizar nombres de variables, tipos, categorías y fechas; validar importes y unidades monetarias; generar datos procesados reproducibles sin exponer información personal.
4. **Mortalidad y supervivencia:** verificar la calidad y representatividad de fechas de fallecimiento/exposición; construir tablas de experiencia cuando la información lo permita; documentar censura, periodo, graduación y limitaciones. Contrastar con tablas externas apropiadas, sin confundirlas con experiencia propia.
5. **Modelo determinístico de la bolsa:** proyectar cohortes y flujos por periodo, incluyendo aportes iniciales, mesadas objetivo, mortalidad/supervivencia, permanencia de remanentes, gastos y una hipótesis explícita de rentabilidad e indexación. Establecer reglas de cálculo, horizonte, tratamiento de supervivientes y condiciones de equilibrio.
6. **Escenarios y sostenibilidad:** variar de forma transparente supuestos de mortalidad, rentabilidad, inflación/SMMLV, composición de participantes y otros parámetros materiales. Reportar métricas de solvencia y suficiencia de activos frente a obligaciones en el tiempo.
7. **Validación y comunicación:** reconciliar identidades de flujo, probar casos límite, someter supuestos a revisión experta y generar tablas, gráficos e interpretaciones automáticas con trazabilidad a entradas y versión del modelo.

La incertidumbre de mortalidad y rentabilidad, simulaciones Monte Carlo y extensiones bayesianas se consideran etapas posteriores; no deben presentarse como resultados de la primera versión determinística.

## Hipótesis y decisiones pendientes

- Definición verificable de “descapitalizado” y población elegible.
- Unidad de análisis, fecha de valoración, edades y tratamiento de beneficiarios.
- Mesada objetivo en términos nominales o reales y regla de actualización con SMMLV/inflación.
- Momento y frecuencia de pago, gastos, comisiones e impuestos.
- Tratamiento de saldos remanentes y de cualquier derecho de beneficiarios.
- Fuente, periodo, credibilidad y ajuste de las hipótesis de mortalidad.
- Rentabilidad neta, estrategia de inversión y correspondencia temporal de activos y obligaciones.
- Métricas de sostenibilidad, nivel de tolerancia y horizonte de proyección.
- Requisitos legales, regulatorios, fiduciarios y de protección al consumidor aplicables.

Estas decisiones requieren validación con las áreas actuariales, jurídicas, de riesgos, inversión, seguridad de la información y gobierno de datos. No se deben asumir implícitamente en el código.

## Referentes conceptuales

- Shemtob, Mark & Stoycheva, Rayna (2023), *Longevity Pooling Variable Pensions*.
- Milevsky, Moshe A. (2017), *Longevity Risk Pooling: Opportunities to Increase Retirement Security*.

Se utilizarán como inspiración conceptual; el modelo deberá adaptarse al contexto colombiano, a la población analizada y a las reglas que se definan. Completar las referencias bibliográficas y verificar sus fuentes antes de citarlas formalmente.

## Productos esperados

- Perfilamiento de población y capitales.
- Análisis documentado de mortalidad/supervivencia y sus limitaciones.
- Modelo determinístico reproducible de flujos de la bolsa.
- Escenarios de sostenibilidad con sensibilidad de supuestos.
- Reportes de tablas y gráficos con interpretaciones automáticas revisables.
- Registro de supuestos, validaciones, decisiones y limitaciones.

## Desarrollo determinístico implementado

La [fase 2](integracion_actuarial.md) implementa una integración sintética de ISC, VPA/RAC y bolsa mensual, con garantía hipotética y sensibilidades. La valoración de obligaciones vitalicias completas y la validación institucional permanecen pendientes.
