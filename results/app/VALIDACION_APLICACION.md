# Validación de la aplicación FINAN

La aplicación fue comprobada con `FraudeDB`, el pipeline Random Forest y el umbral final de 7,22 %. Las pruebas no modificaron las tablas fuente.

## Comprobaciones realizadas

- El proyecto compila sin errores ni advertencias.
- El dashboard muestra 8.914.963 transacciones etiquetadas, 13.332 fraudes y F1 final de 52,7 %.
- La configuración comprueba la conexión a LocalDB y la ruta del ejecutable de Python.
- La transacción 7.984.042 genera una alerta con probabilidad aproximada de 53,85 %.
- La transacción 7.475.327 no genera alerta y obtiene una probabilidad aproximada de 0,02 %.
- Una transacción nueva puede cargarse como ejemplo, modificarse y evaluarse sin insertarla en la base.
- Los factores explicativos se presentan con nombres comprensibles y señalan si aumentan o reducen el riesgo.
- El explorador consulta las tablas y permite cambiar de página.
- La opción de carga masiva no aparece en la interfaz final.
- Cada predicción deja un registro local de resultado, duración y versión del modelo, sin identificadores personales.

## Alcance del monitoreo

El archivo `%LOCALAPPDATA%\FINAN\prediction_monitoring.jsonl` permite revisar el uso básico de la aplicación. No se sube a GitHub porque corresponde a la ejecución de cada equipo.
