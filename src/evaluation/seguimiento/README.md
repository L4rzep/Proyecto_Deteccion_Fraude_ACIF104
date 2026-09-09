# Reproducción del seguimiento

Ejecutar desde la raíz del repositorio. Los resultados versionados son históricos; repetirlos crea nuevas salidas locales. No se reabre el test S9 ni se sobrescribe el modelo de la aplicación.

## 1. Desarrollo S9, entorno de inferencia

Preparar `FraudeDB` con [data/README.md](../../../data/README.md) y el entorno de [README.md](../../../README.md). En PowerShell:

```powershell
& .\.venv-inferencia\Scripts\python.exe src/evaluation/seguimiento/ronda1/extraer_desarrollo.py --output data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz
```

El exportador consulta SQL en modo lectura, reproduce el split con scikit-learn 1.9.0 y verifica filas, clases y SHA-256 de los IDs del test antes de excluirlo. Genera CSV gzip y JSON de procedencia. Deben quedar 841.721 filas y 1.201 fraudes. No se deben completar etiquetas faltantes con cero.

El [manifiesto de referencia](../../../data/reference/desarrollo_s9_manifest.json) identifica la extracción usada en los resultados existentes. Una nueva compresión puede cambiar el SHA-256 del archivo; los scripts verifican el manifiesto de esa extracción y el hash fijo de los IDs excluidos. Si no coinciden los controles, detenerse y revisar la fuente.

## 2. Entorno de experimentos

```powershell
py -3.12 -m venv .venv-experimentos
& .\.venv-experimentos\Scripts\python.exe -m pip install -r requirements-experiments.txt
$env:FINAN_EXPERIMENT_DIR = (Join-Path $PWD 'data/experimentos')
```

R1 verifica y carga la fuente exacta de imbalanced-learn 0.15.dev0 y sklearn_compat en `third_party/ronda1`, con licencias y huellas. No requiere instalar otra versión de ese paquete. R2/R3 utilizan scikit-learn 1.8.0. En Linux/macOS, usar `.venv-experimentos/bin/python` y `export FINAN_EXPERIMENT_DIR="$PWD/data/experimentos"`.

## 3. Comparaciones temporales

```powershell
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/ronda1/comparar_finan.py profile --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/ronda1/comparar_finan.py run --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz --output data/experimentos/finan_ronda1/resultados --jobs 8
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/ronda2/segunda_ronda.py --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz --previous data/experimentos/finan_ronda1 --output data/experimentos/finan_ronda2/experimento --jobs 8
```

R1 ajusta 12 modelos; R2 añade 21. Se guardan modelos, predicciones, métricas y decisiones. Los archivos comprimidos se completan antes de publicar la salida. Las carpetas deben ser nuevas. La evaluación posterior conserva su distribución de clases y cada umbral se fija con validación.

## 4. Contexto y Ronda 3

`transactions_data.csv` es el archivo original de Kaggle. Sustituir la ruta por la ubicación local. El extractor conserva solo IDs presentes en desarrollo; no toma etiquetas de las operaciones sin etiquetar.

```powershell
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/contexto.py --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz --transactions C:/ruta/transactions_data.csv --output data/experimentos/contexto/desarrollo_contexto.csv.gz
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/ronda3/tercera_ronda.py
```

R3 añade seis modelos con contexto cronológico. Necesita las salidas R2 y genera `finan_ronda3/experimento`, con 78 archivos de predicciones para los 13 candidatos × tres años × dos particiones. Las transformaciones temporales usan historia previa; no incorporan etiquetas futuras como variables.

## 5. Costos, umbral y evaluación

```powershell
New-Item -ItemType Directory -Path data/experimentos/finan_decision_costos
Copy-Item results/models/seguimiento/costos/protocolo.json data/experimentos/finan_decision_costos/protocolo.json
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/costos/analizar_costos.py preparar
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/costos/analizar_costos.py seleccionar
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/costos/analizar_costos.py evaluar
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/costos/verificar_costos.py
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/costos/graficar_costos.py
```

En Linux/macOS, sustituir `New-Item` por `mkdir -p` y `Copy-Item` por `cp`. Se conservan separados insumos, decisiones y evaluación. No utilizar `python -O`: desactivaría los controles de consistencia expresados como aserciones.

El verificador recalcula matrices de confusión, todas las curvas y las selecciones económicas desde las predicciones. La ejecución histórica verificó 81 archivos, 39 curvas, 225 decisiones, 135 escenarios y 60 puntos seleccionados de frontera, sin nuevos ajustes. `graficar_costos.py` reproduce las tres figuras PNG/PDF, la identificación del artefacto experimental y la carga mensual complementaria sin cambiar umbrales. Los resultados agregados históricos se conservan en `results/models/seguimiento/costos`.

## 6. Comparación no supervisada

```powershell
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/no_supervisado.py --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz --rf-predictions data/experimentos/finan_ronda2/experimento --output data/experimentos/no_supervisado --jobs 8
& .\.venv-experimentos\Scripts\python.exe src/evaluation/seguimiento/verificar_no_supervisado.py --data data/experimentos/finan_datos_recibidos/finan_desarrollo.csv.gz --rf-predictions data/experimentos/finan_ronda2/experimento --experiment data/experimentos/no_supervisado
```

Son tres ajustes de Isolation Forest. El detector no usa y para entrenar; sus umbrales utilizan etiquetas de validación. La comparación es separada de las 225 decisiones del análisis anterior. No modifica ni promueve modelos de la aplicación.

## 7. Reproducir el entrenamiento S9 sin sustituirlo

Desde el entorno de inferencia y con SQL disponible:

```powershell
& .\.venv-inferencia\Scripts\python.exe src/models/07_train_final_model.py --pipeline-file data/experimentos/reentrenamiento/finan_fraud_pipeline.joblib --schema-file data/experimentos/reentrenamiento/finan_feature_schema.json --metadata-file data/experimentos/reentrenamiento/training_metadata.json
```

El script rechaza salidas existentes. Un nuevo ajuste genera un nuevo artefacto y metadatos propios; no puede recibir automáticamente las métricas del test del modelo original. La evaluación S9 y su archivo de bloqueo se conservan.

## Alcance de la comprobación del cierre

Se validaron los resultados históricos mediante recálculo desde las predicciones, la carga de dependencias R1, los puntos de entrada, el predictor y sus contratos. El nuevo ensayo Isolation Forest sí fue ejecutado. La cadena completa SQL→R1→R2→R3 no se volvió a entrenar desde cero en este cierre; sus resultados corresponden a las ejecuciones registradas. Las rutas adaptadas y el guardado atómico no se presentan como nuevos resultados de rendimiento.
