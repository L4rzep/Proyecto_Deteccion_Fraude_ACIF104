# Proyecto de detección de fraude - ACIF104

Repositorio académico para el desarrollo de una solución de detección de fraude en transacciones mediante aprendizaje automático.

> Estado: el pipeline de Python (extracción → preprocesamiento → entrenamiento → inferencia) y la aplicación C# (`app/Finan`) se ejecutan de punta a punta contra una instancia local de SQL Server. Esquema de base de datos, migraciones y vista maestra verificados y documentados a continuación.

## Estructura

```text
data/                  Datos de referencia y guía de obtención
sql/
  vw_dataset_maestro.sql  Definición de la vista maestra usada en entrenamiento
src/
  data/sql/             SQL asociado al flujo de datos
  models/                Entrenamiento y selección de modelos
  evaluation/            EDA, balanceos y evaluación
  inference/              Inferencia del modelo final
  analisis_fraude.py            Motor de inferencia en producción (invocado por la app C#)
  analisis_fraude-Full Python.py   Pipeline completo de entrenamiento (EDA + modelo)
  fase4_xgboost.py              Variante de entrenamiento con muestra reducida
  migracion_sql.py              Carga de transactions_data.csv a SQL Server
  Migracion_sql_all.py          Carga de transactions_data, users_data, cards_data y JSON (fraud_labels, mcc_codes)
app/Finan/               Aplicación oficial en C# / WinForms
models/                  Modelos y metadatos versionados
results/
  eda/                   Resultados del análisis exploratorio
  models/                Métricas, tablas y curvas
  shap/                  Explicaciones globales y locales
  app/                   Evidencia de funcionamiento de la aplicación (capturas)
  monitoring/             Registro de ejecuciones de FINAN (registro_ejecucion.csv, autogenerado)
  qa/                     Evidencia de control de calidad
tests/
  integration/             Pruebas de integración end-to-end (incluye prueba_integracion.md)
  qa/, smoke/              Otras pruebas
docs/
  formativas/             Entregas formativas S2, S3 y S4
  informe_final/           Informe sumativo y PDF final
  aportes/                 Evidencia de contribuciones del equipo
legacy/                   Material histórico no oficial
```

## Requisitos

- **Python 3.12+** (probado en Python 3.14).
- **SQL Server LocalDB** (o instancia completa de SQL Server) accesible localmente.
- **ODBC Driver 17 for SQL Server**.
- **.NET SDK 10** con soporte para WinForms (target framework `net10.0-windows`), para compilar `app/Finan`.

### Instalación de dependencias Python

Dos opciones según el caso:

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash en Windows
# .\.venv\Scripts\Activate.ps1   # PowerShell

# Opción A: instalación mínima con rangos flexibles
python -m pip install -r requirements.txt

# Opción B: reproducir exactamente el entorno probado por el equipo
python -m pip install -r requirements-lock.txt
```

## 1. Base de datos SQL Server

1. Instalar o confirmar acceso a `(localdb)\MSSQLLocalDB` (o el servidor que corresponda) y crear la base `FraudeDB`.
2. Instalar el **ODBC Driver 17 for SQL Server** si no está presente en el equipo.
3. Cargar los datos base ejecutando, desde `src/`:

   ```bash
   python migracion_sql.py       # Carga transactions_data.csv
   python Migracion_sql_all.py   # Carga transactions_data, users_data, cards_data, fraud_labels y mcc_codes
   ```

   > Ambos scripts insertan en `transactions_data` con `if_exists='append'`. Se verificó (agosto 2026) que correr ambos no genera duplicados en la práctica, pero si se ejecutan varias veces en distinto orden es buena práctica confirmar antes de entrenar:
   > ```sql
   > SELECT id, COUNT(*) AS veces FROM transactions_data GROUP BY id HAVING COUNT(*) > 1;
   > ```

4. Crear la vista maestra ejecutando `sql/vw_dataset_maestro.sql` contra `FraudeDB`. Esta vista es la que consumen los scripts de entrenamiento (`analisis_fraude-Full Python.py`, `fase4_xgboost.py`) y resuelve el cruce entre las 5 tablas base más el renombre de `mcc_codes.description` a `mcc_description`.

   > La vista usa `INNER JOIN` contra `fraud_labels`, `cards_data` y `users_data`: cualquier transacción sin etiqueta de fraude, sin tarjeta o sin usuario coincidente queda excluida del dataset de entrenamiento. Es el comportamiento esperado (no se puede entrenar sin etiqueta), pero explica por qué el conteo de la vista es menor al de `transactions_data` completa.

5. Crear la tabla de resultados de FINAN y su índice ejecutando `C#/SQL/Tabla para FINAN y Indice.sql` contra `FraudeDB`.

### Esquema real de las tablas base

Verificado contra `FraudeDB` en agosto de 2026 (importante porque difiere de nombres asumidos en versiones anteriores del código):

| Tabla | Columnas clave | Notas |
|---|---|---|
| `transactions_data` | `id` (bigint), `date` (datetime2) | **No** se llaman `transaction_id` ni `transaction_date`. |
| `cards_data` | `id` (int), `has_chip` (varchar), `card_on_dark_web` (varchar) | `has_chip`/`card_on_dark_web` vienen como `'Yes'`/`'No'`; se mapean a `1`/`0` explícitamente en el preprocesamiento antes de entrenar. |
| `users_data` | `id` (int) | — |
| `fraud_labels` | `transaction_id` (bigint), `is_fraud` (bit) | Aquí sí se llama `transaction_id` (coincide con `Resultados_Fraude_FINAN`). |
| `mcc_codes` | `mcc` (int), `description` (nvarchar) | No es `mcc_description`; la vista maestra la renombra en la proyección final. |

## 2. Entrenamiento del modelo

Desde `src/`, ejecutar uno de los dos scripts de entrenamiento:

```bash
python "analisis_fraude-Full Python.py"   # Pipeline completo: EDA + entrenamiento (1,000,000 registros por defecto)
python fase4_xgboost.py                    # Entrenamiento directo sin EDA (150,000 registros)
```

Ambos generan `Modelo_Fraude_XGBoost.pkl` en el directorio desde el que se ejecutan (normalmente `src/`).

> El manejo de clases desbalanceadas está en evaluación activa: se compara SMOTE contra `scale_pos_weight` de XGBoost como alternativas. Revisar el reporte de clasificación impreso al final de la ejecución (columna `True` = fraude) antes de considerar un modelo como definitivo para producción.

## 3. Puesta en producción del modelo (integración con la app C#)

La aplicación C# (`app/Finan`) invoca `analisis_fraude.py` como proceso externo (ver `PythonEngine.cs`), resolviendo la ruta del script como `AppDomain.CurrentDomain.BaseDirectory` — es decir, **la carpeta de salida del build**, no `src/`. Pasos:

1. Copiar `Modelo_Fraude_XGBoost.pkl` (generado en el paso anterior) a la carpeta de salida del build de la app C#, por ejemplo:
   ```
   app/Finan/Proyecto_Deteccion_Fraude_ACIF104/Proyecto_Deteccion_Fraude_ACIF104/bin/Debug/net10.0-windows/
   ```
2. Copiar también `src/analisis_fraude.py` a esa misma carpeta.
3. En la app, ir a la pestaña **Configuración** y definir:
   - **Cadena de conexión** a `FraudeDB` (por defecto: `Server=(localdb)\MSSQLLocalDB;Database=FraudeDB;Trusted_Connection=True;`).
   - **Ruta de Python**: ruta absoluta al ejecutable `python.exe` del entorno virtual creado antes.
   - **Umbral de fraude**: valor de corte para las alertas del dashboard.
4. Guardar la configuración (esto prueba la conexión a SQL Server automáticamente).

## 4. Compilar y ejecutar la aplicación C#

```bash
cd app/Finan/Proyecto_Deteccion_Fraude_ACIF104
dotnet build
dotnet run --project Proyecto_Deteccion_Fraude_ACIF104
```

O abrir `Proyecto_Deteccion_Fraude_ACIF104.slnx` directamente en Visual Studio 2022+ con soporte para .NET 10 y WinForms.

## 5. Registro de ejecuciones (monitoreo)

Cada vez que `analisis_fraude.py` procesa un lote (desde la app C# o manualmente), se agrega una fila a `results/monitoring/registro_ejecucion.csv` con timestamp, rango de IDs procesados, cantidad de transacciones, fraudes detectados, duración y estado (`OK`, `SIN_DATOS`, `ERROR_MODELO`, `ERROR_PREDICCION`, `ERROR_GUARDADO`). Este archivo se genera automáticamente; no requiere pasos manuales.

## 6. Pruebas de integración

Ver `tests/integration/prueba_integracion.md` para el procedimiento de prueba end-to-end (carga de CSV → bulk insert → inferencia Python → escritura de resultados → lectura desde el Dashboard de la app).

## Datos

La política y la estructura esperada se describen en `data/README.md`. Los datasets completos, respaldos SQL, credenciales y archivos comprimidos no deben incorporarse al repositorio.

> **Nota sobre `.gitattributes`/`.gitignore`:** `data/FraudeDB.bak` está configurado para Git LFS en `.gitattributes`, pero la regla `*.bak` en `.gitignore` lo excluye globalmente. Si el equipo planea distribuir un respaldo de la base de datos a través del repositorio, esta configuración debe revisarse primero.

## Trabajo colaborativo

Cada cambio debe desarrollarse en una rama identificable, con evidencia verificable y revisión antes de integrarse a `main`. No deben publicarse credenciales, respaldos completos, entornos virtuales ni archivos personales del IDE.
