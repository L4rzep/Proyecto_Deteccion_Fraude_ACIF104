# Preparación y carga de datos en `FraudeDB`

Esta etapa prepara la base de datos del proyecto a partir del dataset público
**Transactions Fraud Datasets**. El procedimiento valida los archivos fuente,
crea las tablas requeridas y carga los datos en SQL Server de forma
reproducible.

Este procedimiento corresponde a la fase inicial de configuración y extracción
de datos del proyecto FINAN. Su resultado es el conjunto de tablas fuente que
alimenta la preparación analítica, el entrenamiento del modelo y, finalmente,
la integración con la aplicación.

Fuente pública:
<https://www.kaggle.com/datasets/computingvictor/transactions-fraud-datasets/data>

## Archivos del procedimiento

| Archivo | Función |
|---|---|
| `src/data/inspect_source_data.py` | Comprueba la presencia y estructura de los cinco archivos fuente, cuenta sus registros y calcula sus huellas SHA-256. |
| `src/data/sql/01_create_source_tables.sql` | Crea las cinco tablas fuente con sus claves primarias si todavía no existen. |
| `src/data/load_source_data.py` | Carga los archivos CSV y JSON por lotes en SQL Server y omite las tablas que ya contienen registros. |

## Correspondencia de datos

| Archivo fuente | Tabla SQL | Registros validados |
|---|---|---:|
| `users_data.csv` | `dbo.users_data` | 2.000 |
| `cards_data.csv` | `dbo.cards_data` | 6.146 |
| `transactions_data.csv` | `dbo.transactions_data` | 13.305.915 |
| `train_fraud_labels.json` | `dbo.fraud_labels` | 8.914.963 |
| `mcc_codes.json` | `dbo.mcc_codes` | 109 |

Las etiquetas cubren solamente una parte de las transacciones. Por esta razón,
las tablas fuente no incorporan una clave foránea obligatoria entre
`transactions_data` y `fraud_labels`.

## Entorno utilizado para la carga

La validación y la carga de datos se ejecutaron desde Visual Studio Code,
utilizando su terminal PowerShell integrada y un entorno virtual de Python
aislado (`.venv`). SQL Server Management Studio se utilizó para crear la base,
ejecutar el archivo SQL y comprobar las cantidades cargadas.

- Windows 10 de 64 bits.
- Visual Studio Code 1.131.0.
- Python 3.11.9.
- `pyodbc` 5.3.0.
- SQL Server 2025 Express 17.0.1125.2.
- ODBC Driver 17 for SQL Server.
- SQL Server Management Studio 22.8.1.

Las rutas locales pueden variar entre integrantes. Los comandos utilizan
`C:\ruta\al\dataset` como marcador para la carpeta que contiene los cinco
archivos fuente.

Estas versiones corresponden a la preparación y carga de datos. Las
dependencias del modelamiento y del backend se documentan en sus componentes
respectivos.

## Preparación del entorno en Visual Studio Code

Abrir la carpeta raíz del repositorio en Visual Studio Code y seleccionar
**Terminal > Nuevo terminal**. En la terminal PowerShell integrada:

```powershell
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install pyodbc==5.3.0
```

La carpeta `.venv` es local y no se versiona.

## Procedimiento de preparación y carga

### 1. Crear la base de datos

Conectarse mediante autenticación de Windows al servidor
`(localdb)\MSSQLLocalDB`. Si la base todavía no existe, ejecutar en SSMS:

```sql
CREATE DATABASE [FraudeDB];
GO
```

### 2. Validar los archivos fuente

```powershell
& ".\.venv\Scripts\python.exe" `
  ".\src\data\inspect_source_data.py" `
  --source-dir "C:\ruta\al\dataset"
```

La ejecución correcta termina con `ARCHIVOS FUENTE VÁLIDOS` y presenta las
cantidades y huellas SHA-256 de los cinco archivos.

### 3. Crear las tablas

Abrir `src/data/sql/01_create_source_tables.sql` en SSMS. En el desplegable de
base de datos situado en la barra superior de la misma pestaña, seleccionar
`FraudeDB` y presionar **Ejecutar**.

El script crea:

- `dbo.users_data`
- `dbo.cards_data`
- `dbo.transactions_data`
- `dbo.fraud_labels`
- `dbo.mcc_codes`

### 4. Cargar los datos

Ejecutar desde la terminal PowerShell integrada de Visual Studio Code:

```powershell
& ".\.venv\Scripts\python.exe" `
  ".\src\data\load_source_data.py" `
  --source-dir "C:\ruta\al\dataset" `
  --server "(localdb)\MSSQLLocalDB" `
  --database "FraudeDB" `
  --driver "ODBC Driver 17 for SQL Server"
```

El cargador informa el avance cada 50.000 filas y entrega un resumen final por
tabla.

### 5. Verificar las cantidades

Ejecutar en SSMS con `FraudeDB` como base activa:

```sql
SELECT 'users_data' AS tabla, COUNT_BIG(*) AS filas
FROM dbo.users_data
UNION ALL
SELECT 'cards_data', COUNT_BIG(*)
FROM dbo.cards_data
UNION ALL
SELECT 'transactions_data', COUNT_BIG(*)
FROM dbo.transactions_data
UNION ALL
SELECT 'fraud_labels', COUNT_BIG(*)
FROM dbo.fraud_labels
UNION ALL
SELECT 'mcc_codes', COUNT_BIG(*)
FROM dbo.mcc_codes;
```

Resultado esperado:

```text
users_data             2.000
cards_data             6.146
transactions_data     13.305.915
fraud_labels           8.914.963
mcc_codes                109
```

### 6. Comprobar la repetición segura

Ejecutar nuevamente el comando del paso 4. Las cinco tablas deben aparecer como
`omitida; ya contiene ... filas`, sin alterar las cantidades verificadas.

## Validación realizada

El procedimiento completo fue ejecutado sobre una `FraudeDB` vacía y produjo
los siguientes resultados:

- cinco archivos fuente validados por estructura, cantidad y SHA-256;
- cinco tablas creadas con sus claves primarias;
- 22.229.133 filas cargadas, sumadas entre todas las tablas; y
- segunda ejecución finalizada sin duplicar registros.

## Relación con las etapas del proyecto

El flujo técnico del proyecto sigue esta secuencia:

1. validar los archivos públicos y cargarlos en las tablas fuente de SQL Server;
2. integrar las tablas y preparar las variables mediante una vista analítica;
3. realizar el análisis exploratorio y generar una muestra reproducible;
4. entrenar, comparar y evaluar los modelos de aprendizaje automático;
5. serializar el modelo seleccionado; y
6. integrar el modelo y la base de datos con la aplicación FINAN.

Este README documenta el primer punto. La base resultante proporciona la entrada
necesaria para construir `vw_dataset_maestro`, utilizada posteriormente para el
análisis exploratorio, el modelamiento y la inferencia.

Las tablas fuente conservan los nombres originales: `transactions_data.id`,
`transactions_data.date` y `mcc_codes.description`. La vista analítica
estandariza estos campos como `transaction_id`, `transaction_date` y
`mcc_description`, manteniendo las fuentes intactas y entregando una interfaz
estable a los componentes siguientes.

## Archivos incluidos en GitHub

Se incluyen en el repositorio:

- los scripts Python de validación y carga;
- el script SQL de creación de tablas; y
- la documentación necesaria para repetir el procedimiento.

No se incluyen los CSV y JSON completos, los archivos locales de SQL Server
(`*.mdf` y `*.ldf`), respaldos `*.bak`, archivos comprimidos ni `.venv`, porque
son archivos locales o de gran tamaño. Los datos se obtienen desde el enlace
público indicado al comienzo y se cargan mediante los scripts versionados.

Tampoco se incorporan credenciales ni rutas personales. Los resultados
agregados y artefactos necesarios para evaluar las etapas siguientes se
documentan en sus carpetas correspondientes.
