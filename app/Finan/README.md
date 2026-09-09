# Aplicación FINAN

FINAN permite consultar las transacciones almacenadas en `FraudeDB` y evaluar una transacción existente o nueva con el modelo final. La predicción muestra la probabilidad estimada, el nivel de riesgo y los factores que más influyeron en el resultado.

## Requisitos

- Windows con .NET 10.
- `FraudeDB` disponible en SQL Server o LocalDB.
- Python 3.12 con las dependencias de `requirements-inference.txt`, en un entorno separado de los experimentos.
- ODBC Driver 17 for SQL Server.

## Ejecución

Desde la carpeta raíz del repositorio:

```powershell
py -3.12 -m venv .venv-inferencia
& .\.venv-inferencia\Scripts\python.exe -m pip install -r requirements-inference.txt
dotnet restore ".\app\Finan\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104.csproj"
dotnet run --project ".\app\Finan\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104\Proyecto_Deteccion_Fraude_ACIF104.csproj"
```

En **Configuración** se debe indicar:

- la conexión a `FraudeDB`, por ejemplo `Server=(localdb)\MSSQLLocalDB;Database=FraudeDB;Trusted_Connection=True;`;
- la ruta de `python.exe` del entorno donde se instalaron las dependencias.

El proyecto copia al directorio de ejecución el predictor, el pipeline Random Forest, su esquema de variables y las métricas finales. La prueba anterior de XGBoost se conserva en [`legacy/modelos/`](../../legacy/modelos/README.md). La identidad del Random Forest servido se registra en [`models/MODELO_OFICIAL.json`](../../models/MODELO_OFICIAL.json).

## Funciones principales

- **Dashboard:** resume el conjunto etiquetado y el F1 obtenido en el test final.
- **Explorador:** permite revisar las tablas fuente por páginas.
- **Configuración:** comprueba la conexión y guarda la ruta de Python.
- **Predicción:** evalúa un ID existente o una transacción nueva y explica el resultado.

## Decisión sobre Carga & Lotes

La pantalla **Carga & Lotes** se diseñó inicialmente para importar archivos CSV y probar la carga masiva desde la aplicación durante las primeras etapas de integración.

En la versión final esta pantalla se mantiene en el código, pero se oculta de la interfaz. `FraudeDB` ya cuenta con un proceso de preparación y carga reproducible en `src/data`, por lo que permitir inserciones directas desde dos mecanismos distintos duplicaría funciones y podría alterar accidentalmente los datos utilizados por el modelo. La aplicación se concentra en consultar datos y evaluar transacciones sin modificar las tablas de origen.

## Monitoreo básico

Cada evaluación registra fecha, origen, duración, resultado y versión del modelo. Si ocurre un error, también queda registrado. No se guardan identificadores de clientes, tarjetas ni transacciones.

El registro se crea en `%LOCALAPPDATA%\FINAN\prediction_monitoring.jsonl`. Este archivo permite revisar cuántas evaluaciones se realizaron, cuántas generaron alertas, el tiempo promedio y los errores ocurridos.

Las comprobaciones funcionales históricas se resumen en [`results/app/VALIDACION_APLICACION.md`](../../results/app/VALIDACION_APLICACION.md). Las pruebas automatizadas actuales del backend, sus tiempos y su alcance se documentan en [requisitos y pruebas](../../docs/REQUISITOS_Y_PRUEBAS.md). La interfaz Windows y la conexión SQL no se volvieron a ejecutar en el cierre de septiembre; las pruebas del backend usan entradas JSON sintéticas.
