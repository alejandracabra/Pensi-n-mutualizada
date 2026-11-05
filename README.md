# Pensión mutualizada

Proyecto de investigación aplicado para evaluar la viabilidad actuarial y financiera de una modalidad de pensión mutualizada dirigida a afiliados con cuentas de ahorro individual descapitalizadas en Colombia.

> **Confidencialidad:** la información de afiliados y los archivos fuente no deben publicarse en GitHub. Este repositorio excluye archivos Excel y el contenido de las carpetas de datos y resultados. Verifique siempre que no existan datos personales, identificadores ni información corporativa antes de compartir código, reportes o gráficos.

## Objetivo

Generar evidencia cuantitativa sobre la sostenibilidad de una bolsa colectiva que recibe el capital disponible de los participantes y financia una mesada objetivo de 1 SMMLV, considerando la mutualización del riesgo de longevidad. El diseño y sus supuestos deben validarse con las áreas actuariales, jurídicas y de cumplimiento correspondientes; este análisis académico no constituye asesoría ni una propuesta aprobada de producto.

## Estructura

```text
.
├── data/
│   ├── raw/                 # Fuentes originales, no versionadas
│   ├── processed/           # Datos derivados, no versionados
│   └── external/            # Tablas y fuentes externas
├── notebooks/               # Análisis exploratorios y experimentales
├── src/
│   ├── data/                # Ingesta y validación
│   ├── features/            # Transformaciones y variables analíticas
│   ├── actuarial/           # Mortalidad, supervivencia y cálculos actuariales
│   ├── simulation/          # Escenarios y futuras simulaciones
│   ├── visualization/       # Gráficos y reportes
│   └── utils/               # Utilidades comunes
├── reports/
│   ├── figures/             # Gráficos exportados
│   ├── tables/              # Tablas exportadas
│   └── outputs/             # Reportes generados (no versionados)
├── docs/
│   ├── literatura/
│   ├── reuniones/
│   └── tesis/
└── dashboard/
```

El notebook `notebooks/01_exploracion.ipynb` contiene el EDA inicial y genera `reports/exploracion.html` y `reports/exploracion.md`; los notebooks `02` a `06` se conservan como plantillas para las etapas posteriores. `Proyecto_Grado.ipynb` se conserva como material de trabajo y busca `Base_Proyecto.xlsx` en `data/raw/` y en la raíz del proyecto (también al ejecutarlo desde `notebooks/`). Para mantener una estructura limpia, se recomienda guardar localmente el archivo fuente en `data/raw/`.

## Requisitos

- Python 3.11 o superior.
- Dependencias de `requirements.txt`.
- Jupyter Notebook o JupyterLab.

## Instalación

Desde la raíz del repositorio, cree un entorno virtual e instale las dependencias:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Abra el proyecto en VS Code y seleccione el intérprete de `.venv`. En macOS/Linux, active el entorno con `source .venv/bin/activate`.

## Datos y ejecución

1. Obtenga autorización para usar los datos y trabaje únicamente en el entorno aprobado.
2. Mantenga los archivos originales en `data/raw/` (o en su ubicación local actual); no los agregue a Git.
3. Use los notebooks en orden y conserve las fuentes originales sin modificaciones.
4. Documente cada transformación y cada supuesto actuarial.
5. Inspeccione los resultados para detectar datos identificables antes de exportar o compartir.

El EDA se ejecuta en `notebooks/01_exploracion.ipynb`; los reportes y sus agregados locales no se versionan por defecto. El notebook previo `Proyecto_Grado.ipynb` busca `Base_Proyecto.xlsx` en la raíz o en `data/raw/`.

Para ejecutar el EDA desde la raíz del proyecto:

```powershell
jupyter lab notebooks/01_exploracion.ipynb
```

Ejecute las celdas en orden. Se generan `reports/exploracion.html` (dashboard autocontenido, con Plotly embebido) y `reports/exploracion.md`. Para validar los módulos:

```powershell
python -m unittest discover -s tests -v
```

### Visualizaciones ejecutivas

Para generar el paquete de figuras 16:9 para presentaciones, junto con sus versiones PNG (300 dpi), SVG, el HTML ejecutivo y la tabla descriptiva:

```powershell
python -m src.visualization.executive
```

Los archivos se guardan en `reports/outputs/presentacion_ejecutiva/figures/`, `reports/exploracion_ejecutiva.html` y `reports/tables/`. El HTML exploratorio original no se sobrescribe. Los resultados generados y los datos de afiliados permanecen excluidos de Git.

## Referencias iniciales

- Shemtob, M. & Stoycheva, R. (2023). *Longevity Pooling Variable Pensions*.
- Milevsky, M. A. (2017). *Longevity Risk Pooling: Opportunities to Increase Retirement Security*.

Consulte `docs/proyecto.md` para el planteamiento y la metodología preliminar. Las referencias deben verificarse y completarse con su información bibliográfica antes de la entrega académica.

## Conexión posterior con GitHub

Antes de publicar, revise los archivos que se agregarán y cree el commit inicial:

```powershell
git add .
git status
git diff --cached --check
git commit -m "Initial project structure"
```

Después de crear un repositorio remoto privado y confirmar que no se incluirán datos sensibles:

```powershell
git remote add origin https://github.com/ORGANIZACION/pension-mutualizada.git
git push -u origin main
```

No agregue archivos de datos con `git add -f`. Revise `git status` y `git diff --cached` antes de cada commit.

## Estado

Estructura inicial del proyecto. La estimación de mortalidad, el modelo mutualizado, los escenarios y la generación automática de reportes se desarrollarán y validarán en etapas posteriores.

## Piloto sintético de mutualización

Ver [revisión inicial](docs/revision_inicial.md) y [supuestos, límites y ejecución](docs/piloto_mutualizacion.md). Ejecutar `python -m src.simulation.pilot` desde la raíz. No utiliza datos reales ni concluye viabilidad.
