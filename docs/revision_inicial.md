# Revisión inicial y prioridades

Se conserva la estructura y las API existentes. Inventario al inicio del refactor:

- `src/actuarial/eligibility.py`: `calculate_isc`, `calculate_eligibility_scenarios`, `isc_data_quality`, `eligibility_figures`.
- `src/data/loader.py`: `_normalize_header`, `normalize_columns`, `find_workbook`, `load_workbook`.
- `src/data/profile.py`: `numeric_columns`, `categorical_columns`, `datetime_columns`, `overview_table`, `numeric_summary`, `iqr_outlier_summary`, `safe_category_counts`.
- `src/utils/reporting.py`: `_number`, `_is_affirmative`, `_affirmative_rate`, `calculate_kpis`, `_format_number`, `_format_money`, `_variable_label`, `_association_strength`, `_spearman_correlation`, `_distribution_statistics`, `_describe_distribution`, `_describe_categorical`, `_describe_association`, `column_is_financial`, `_chart_interpretation`, `_interpretation_html`, `_isc_scenarios_html`, `_table_markdown`, `automatic_findings`, `build_markdown_report`, `_kpi_cards`, `_dashboard_filter`, `build_dashboard_html`, `write_reports`.
- `src/visualization/eda.py`: `_numeric`, `_format_millions`, `_format_money`, `_histogram`, `_log_histogram`, `_density_curve`, `distribution_figures`, `financial_status_histograms`, `completeness_figures`, `categorical_figures`, `risk_hierarchy_figures`, `coverage_band`, `coverage_figure`, `binned_relationship`, `scatter_matrix_figure`, `financial_correlation_figure`, `financial_violin_figures`.
- `src/visualization/executive.py`: `ExecutiveChart`, `_format_integer`, `_format_decimal`, `_format_millions`, `_format_billions`, `_clean_axis`, `_canvas`, `_applicable_frame`, `_base_metadata`, `_composition_chart`, `_age_chart`, `_capital_chart`, `_isc_segments`, `_isc_segment_chart`, `_capital_scenarios_chart`, `_candidate_expansion_chart`, `build_executive_charts`, `_summary_frame`, `_summary_markdown`, `_executive_html`, `generate_executive_package`.

## Notebooks y etapas pendientes

- `notebooks\01_exploracion.ipynb`: 9 celdas de código; # 01 · Exploración de datos; ## 1. Configuración y carga; ## 2. Estadísticas generales y diccionario observado; ## 3. Calidad y valores extremos; ## 4. Análisis demográfico; ## 5. Análisis financiero; ## 6. Riesgos y participación; ## 7. Relaciones entre variables; ## 8. Indicadores iniciales y cobertura experimental; ## 9. Exportación del dashboard y el informe Markdown; ## Interpretación y límites
- `notebooks\02_limpieza.ipynb`: 0 celdas de código;
- `notebooks\03_caracterizacion.ipynb`: 0 celdas de código;
- `notebooks\04_supervivencia.ipynb`: 0 celdas de código;
- `notebooks\05_modelo_mutualizado.ipynb`: 0 celdas de código;
- `notebooks\06_escenarios.ipynb`: 0 celdas de código;
- `Proyecto_Grado.ipynb`: 4 celdas de código;

## Orden de trabajo

1. Eliminar conclusiones y cifras fijas de títulos; centralizar paleta y corregir unidades.
2. Explicitar universo ISC, calculabilidad y clasificación; conservar exclusiones y umbrales. Separar grupos acumulados de intervalos excluyentes.
3. Incorporar bolsa cerrada sintética con parámetros separados y conciliación de flujos.
4. Probar identidades, límites ISC, cohortes, agotamiento y generación de artefactos.
5. Pendiente: deduplicación y unidad persona, mortalidad calibrada, beneficiarios, calibración de gastos/rendimientos, escenarios estocásticos, revisión actuarial y normativa. Los notebooks 02–06 no constituyen etapas validadas.

No se cargan datos reales, no se generan resultados corporativos, no se hacen commits ni push.
