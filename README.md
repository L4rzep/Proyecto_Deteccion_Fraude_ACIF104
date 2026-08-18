# Proyecto de detección de fraude - ACIF104

FINAN es una solución académica para detectar posibles fraudes en transacciones. El repositorio contiene el proceso reproducible de datos, el análisis exploratorio, la comparación de modelos, la evaluación final, las explicaciones SHAP y una aplicación de escritorio.

> Estado: el flujo técnico y la aplicación están integrados y verificados. El informe final debe utilizar las métricas y evidencias versionadas en `results/`.

## Estructura

```text
data/                  Datos de referencia y guía de obtención
src/
  data/sql/            SQL asociado al flujo de datos
  models/              Entrenamiento y selección de modelos
  evaluation/          EDA, balanceos y evaluación
  inference/           Inferencia del modelo final
app/Finan/             Aplicación de escritorio FINAN
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

Los archivos oficiales se encuentran en `src/data`, `src/evaluation`, `src/models` y `src/inference`. Los scripts anteriores que se mantienen fuera de esas carpetas sirven como antecedente y no corresponden al flujo final.

## Requisitos

- Python y las bibliotecas enumeradas en `requirements.txt`.
- SQL Server o LocalDB con acceso a la base utilizada por el proyecto.
- Controlador ODBC para SQL Server.
- .NET 10 para la aplicación WinForms.

## Preparación preliminar de Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Datos

El procedimiento verificado de obtención, validación, carga y preparación analítica se describe en [`data/README.md`](data/README.md). Los datasets completos, respaldos SQL, credenciales y archivos comprimidos no deben incorporarse al repositorio.

## Flujo del proyecto

El orden seguido fue:

1. preparar `FraudeDB` y crear las vistas analíticas;
2. generar el EDA y revisar las variables candidatas;
3. comparar variables, balanceos, tres modelos de ML y tres arquitecturas de DL;
4. seleccionar y refinar Random Forest;
5. entrenar el pipeline final sin utilizar el conjunto de prueba;
6. evaluar una sola vez las 148.540 transacciones reservadas;
7. generar explicaciones SHAP e integrar el modelo con FINAN.

Cada carpeta de resultados contiene un README con las decisiones, métricas y archivos generados. Los comandos de datos están en [`data/README.md`](data/README.md), los resultados del modelamiento en [`results/models/README.md`](results/models/README.md) y la aplicación en [`app/Finan/README.md`](app/Finan/README.md).

## Aplicación FINAN

La aplicación consulta `FraudeDB`, muestra un resumen del conjunto etiquetado y permite evaluar una transacción existente o una nueva. La salida informa la probabilidad, el nivel de riesgo y los factores que más influyeron.

```powershell
dotnet run --project ".\app\Finan\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104.csproj"
```

En la pestaña **Configuración** se registra la conexión a `FraudeDB` y la ruta del Python donde se instalaron las dependencias. El modelo, su esquema y las métricas finales se copian automáticamente a la carpeta de ejecución.

## Documentación

- `docs/formativas/s2/`: problemática, requisitos y planificación inicial.
- `docs/formativas/s3/`: EDA, técnicas candidatas y balanceo.
- `docs/formativas/s4/`: arquitectura, resultados preliminares y despliegue.
- `docs/informe_final/`: informe sumativo consolidado y PDF final.

## Trabajo colaborativo

Cada cambio debe desarrollarse en una rama identificable, con evidencia verificable y revisión antes de integrarse a `main`. No deben publicarse credenciales, respaldos completos, entornos virtuales ni archivos personales del IDE.
