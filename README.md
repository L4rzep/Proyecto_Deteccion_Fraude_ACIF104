# Proyecto de detección de fraude - ACIF104

Repositorio académico para el desarrollo de una solución de detección de fraude en transacciones mediante aprendizaje automático.

> Estado preliminar: la estructura del repositorio se está alineando con la rúbrica de la Evaluación Sumativa 1. La definición del entrenamiento, la inferencia y la aplicación oficiales todavía debe ser confirmada por el equipo.

## Estructura

```text
data/                  Datos de referencia y guía de obtención
src/
  data/sql/            SQL asociado al flujo de datos
  models/              Entrenamiento y selección de modelos
  evaluation/          EDA, balanceos y evaluación
  inference/           Inferencia del modelo final
app/Finan/             Ubicación prevista para la aplicación oficial
models/                Modelos y metadatos versionados
results/
  eda/                 Resultados del análisis exploratorio
  models/              Métricas, tablas y curvas
  shap/                Explicaciones globales y locales
  app/                 Evidencia de funcionamiento de la aplicación
tests/                 Pruebas y validaciones mínimas
docs/
  formativas/          Entregas formativas S2, S3 y S4
  informe_final/       Informe sumativo y PDF final
  aportes/             Evidencia de contribuciones del equipo
legacy/                Material histórico no oficial
```

Los scripts Python, el modelo PKL, la aplicación C#, los archivos SQL y sus recursos mantienen temporalmente sus ubicaciones actuales hasta que el equipo confirme cuáles serán las fuentes oficiales.

## Requisitos preliminares

- Python y las bibliotecas enumeradas en `requirements.txt`.
- SQL Server o LocalDB con acceso a la base utilizada por el proyecto.
- Controlador ODBC para SQL Server.
- Entorno .NET compatible con la aplicación WinForms.

Las versiones exactas deben registrarse después de confirmar el entorno utilizado para generar el modelo final.

## Preparación preliminar de Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Datos

La política y la estructura esperada se describen en `data/README.md`. Los datasets completos, respaldos SQL, credenciales y archivos comprimidos no deben incorporarse al repositorio.

## Ejecución

Los comandos oficiales de entrenamiento, evaluación, inferencia y aplicación se incorporarán cuando el equipo consolide el pipeline final. No se debe asumir que los scripts históricos o experimentales representan la versión definitiva.

## Documentación

- `docs/formativas/s2/`: problemática, requisitos y planificación inicial.
- `docs/formativas/s3/`: EDA, técnicas candidatas y balanceo.
- `docs/formativas/s4/`: arquitectura, resultados preliminares y despliegue.
- `docs/informe_final/`: ubicación reservada para la entrega sumativa consolidada.

## Trabajo colaborativo

Cada cambio debe desarrollarse en una rama identificable, con evidencia verificable y revisión antes de integrarse a `main`. No deben publicarse credenciales, respaldos completos, entornos virtuales ni archivos personales del IDE.
