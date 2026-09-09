# FINAN · Detección de fraude · ACIF104

FINAN integra preparación de datos, comparación de modelos, explicaciones SHAP y una aplicación C# Windows Forms. Su alcance es académico: apoyar la revisión humana de transacciones.

El modelo oficial es el **Random Forest evaluado en Semana 9**. El seguimiento estudia costos, balanceo y estabilidad temporal; no justifica reemplazar automáticamente ese artefacto ni acredita operación bancaria autónoma.

## Modelo, evaluación y aplicación

| Elemento | Fuente oficial |
|---|---|
| Identidad y rutas | [MODELO_OFICIAL.json](models/MODELO_OFICIAL.json) |
| Pipeline | [finan_fraud_pipeline.joblib](models/finan_fraud_pipeline.joblib) |
| Entradas y umbral | [finan_feature_schema.json](models/finan_feature_schema.json) |
| Entrenamiento | [07_train_final_model.py](src/models/07_train_final_model.py), [metadatos](results/models/final_model_training_metadata.json) |
| Test S9 | [Métricas](results/models/final_test_metrics.json), [metadatos de evaluación](results/models/final_test_evaluation_metadata.json) |
| Inferencia | [predict_transaction.py](src/inference/predict_transaction.py) |
| Aplicación | [app/Finan](app/Finan/README.md) |

Configuración: 200 árboles, profundidad máxima 16, mínimo dos muestras por hoja, semilla 42, 22 entradas y 178 columnas procesadas. Umbral `0.07217143`. SHA-256 del pipeline: `3b7d4d0d0b557dddd4ff13fa2865ac32365efd5377da059a5cb96db1db1ad178`.

| Evaluación original S9 | Resultado |
|---|---:|
| Transacciones / fraudes del test | 148.540 / 212 |
| TP / FP / FN / TN | 87 / 31 / 125 / 148.297 |
| Precisión / recall / F1 | 0,737288 / 0,410377 / 0,527273 |
| PR-AUC / ROC-AUC | 0,478198 / 0,939748 |

El test se evaluó una sola vez. Sus identificadores se excluyen del seguimiento. Los modelos y umbrales temporales no son intercambiables con el artefacto S9. El score no cuenta con un estudio de calibración para uso productivo.

## Instalación y comprobación del predictor

Desde la raíz del repositorio, en PowerShell:

```powershell
py -3.12 -m venv .venv-inferencia
& .\.venv-inferencia\Scripts\python.exe -m pip install -r requirements-inference.txt
& .\.venv-inferencia\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv-inferencia\Scripts\python.exe src/inference/predict_transaction.py --input-json tests/fixtures/transaccion_sintetica.json --explain
```

En Linux/macOS, crear el entorno con `python3 -m venv .venv-inferencia` y utilizar `.venv-inferencia/bin/python`. La prueba JSON no necesita SQL Server y usa una transacción sintética.

Inferencia utiliza scikit-learn 1.9.0, correspondiente al modelo. El seguimiento usa otro entorno con scikit-learn 1.8.0: [reproducción de experimentos](src/evaluation/seguimiento/README.md). `requirements.txt` conserva las dependencias históricas ML/DL; CUDA no es necesario para ejecutar el predictor.

## Aplicación

Requiere Windows, .NET 10, ODBC y `FraudeDB` preparada según [data/README.md](data/README.md).

```powershell
dotnet run --project app/Finan/Proyecto_Deteccion_Fraude_ACIF104/Proyecto_Deteccion_Fraude_ACIF104/Proyecto_Deteccion_Fraude_ACIF104.csproj
```

En **Configuración**, indicar la conexión a `FraudeDB` y el ejecutable Python del entorno de inferencia. La aplicación copia predictor, pipeline, esquema y métricas al directorio de ejecución. Permite consultar, evaluar transacciones existentes/nuevas y mostrar factores SHAP.

La integración Windows/SQL tiene [evidencia manual histórica](results/app/VALIDACION_APLICACION.md). El cierre agrega diez pruebas automáticas del contrato y predictor y una microprueba de 36 solicitudes con SHAP; esta última no mide SQL, WinForms ni disponibilidad continua. Véase [requisitos y pruebas](docs/REQUISITOS_Y_PRUEBAS.md).

## Seguimiento de recall y costo

El [análisis consolidado](results/models/seguimiento/README.md) incluye tres estrategias reales frente al desbalance, validación temporal, matriz de costos, capacidad mensual, sensibilidad, variables de comportamiento e Isolation Forest.

En el escenario principal de 2019, el RF temporal seleccionado detecta 12 de 123 fraudes con 160 FP. Una alternativa de mayor carga detecta 17, pero su ahorro calculado frente a no alertar es solo 2,07 u. m. y supera la capacidad en seis meses. Son resultados retrospectivos con costos hipotéticos; no demuestran una mejora del recall del modelo S9 ni viabilidad futura garantizada.

## Organización

| Ruta | Contenido |
|---|---|
| `src/data/`, `data/reference/` | Carga, vistas, diccionario y manifiesto de desarrollo |
| `src/models/`, `results/models/` | Variables, balanceo, 3 ML, 3 MLP y RF final |
| `src/evaluation/seguimiento/`, `results/models/seguimiento/` | Experimentos temporales y económicos |
| `results/eda/`, `results/shap/` | EDA y explicaciones del modelo evaluado |
| `app/Finan/`, `src/inference/`, `tests/` | Interfaz, predictor y pruebas |
| [docs/METODOLOGIA.md](docs/METODOLOGIA.md) | Fases, iteraciones y planificación |
| [docs/informe_final](docs/informe_final/README.md) | Estado de las entregas documentales |
| [legacy/modelos](legacy/modelos/README.md) | Artefactos históricos fuera del flujo oficial |
| `third_party/ronda1/` | Dependencia de balanceo de R1 con licencias y huellas |

La recuperación del artefacto S9 mantiene la correspondencia entre modelo y métricas; no constituye una comparación predictiva contra el reentrenamiento de septiembre, que se conserva en `legacy`.

Datasets completos, respaldos SQL, credenciales, entornos y archivos personales del IDE se mantienen fuera del repositorio. Cada cambio se realiza en una rama identificable y se revisa antes de integrarlo a `main`.
