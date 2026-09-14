# Calidad de datos de las 38 variables

La ejecución del 13 de septiembre de 2026 documenta la completitud de las 38 variables de `dbo.vw_dataset_maestro` y ocho controles de calidad sobre sus **8.914.963 transacciones etiquetadas**. Los tres resultados completos permiten consultar las mediciones que antes estaban respaldadas parcialmente por una captura.

## Archivos y reproducción

| Archivo | Contenido |
|---|---|
| [01_resumen_general.csv](01_resumen_general.csv) | Población etiquetada, clases y fechas |
| [02_completitud_38_variables.csv](02_completitud_38_variables.csv) | Total, nulos y porcentaje por variable |
| [03_controles_calidad.csv](03_controles_calidad.csv) | Ocho controles y sus interpretaciones |
| [ejecucion.json](ejecucion.json) | Fecha, base, consulta, alcance y huellas SHA-256 |

La consulta utilizada es [01_profile_data_quality.sql](../../../src/evaluation/sql/01_profile_data_quality.sql). Se ejecuta sobre `FraudeDB`, con `dbo.vw_dataset_maestro` ya creada, y devuelve tres resultados. Es de solo lectura; no crea ni modifica tablas, vistas ni modelos. No hace falta repetir esta extracción para consultar la evidencia publicada.

El registro de escritorio identifica el commit `deb64c1d630b4c97d1318ff9a727dc1e1c377c04`. Se comprobó que el SQL es idéntico al de `546371beadd74b9a85df885f380e9299213d7502`, que incorpora el PR12: SHA-256 `f5bcb191c68d27376364d94e53dbf8edb3cc4014c18bae9683304360734cbee5`. La diferencia entre esos commits no altera esta consulta. El registro publicado conserva las huellas originales de los tres CSV y sustituye únicamente dos rutas absolutas locales por referencias relativas; también identifica la huella del registro original.

## Resultados

Hay **13.332 fraudes y 8.901.631 operaciones sin fraude**, equivalentes a una tasa de fraude de **0,149546 %**. Las transacciones abarcan desde `2010-01-01 00:01:00` hasta `2019-10-31 23:57:00`.

De las 38 variables, 34 no presentan nulos. Las cuatro restantes son:

| Variable | Filas nulas | Porcentaje nulo |
|---|---:|---:|
| `amount_to_credit_limit` | 35.689 | 0,400327 % |
| `merchant_state` | 1.047.865 | 11,754003 % |
| `merchant_zip` | 1.107.377 | 12,421555 % |
| `years_since_pin_change` | 1.293.579 | 14,510200 % |

`transaction_id`, `transaction_date`, `client_id`, `card_id`, `merchant_id`, `mcc_description` e `is_fraud` tienen **cero nulos** en esta población. La ausencia de una medición en el análisis de candidatos anterior no debe interpretarse como presencia de nulos.

Los ocho controles coinciden con los recuentos generales ya documentados en el [EDA](../README.md). Sus resultados pueden solaparse y no deben sumarse para estimar transacciones únicas con problemas. Los montos negativos se conservan como posibles devoluciones; no se eliminan automáticamente.

## Alcance de la medición

Esta medición cubre toda la vista etiquetada. El análisis histórico de candidatos y los gráficos de montos usan una muestra de **990.261 transacciones**; sus porcentajes tienen otro denominador y se mantienen como resultados de esa muestra. Las filas `not_analyzed` de `feature_candidate_assessment.csv` describen el alcance de aquel análisis de candidatos, no el estado de esta nueva medición de completitud.

La completitud no acredita por sí sola exactitud, unicidad, validez temporal ni capacidad predictiva. Las 38 columnas incluyen identificadores y la etiqueta objetivo; no equivalen a 38 entradas del modelo. Esta incorporación documental conserva el modelo oficial de 22 entradas, sus métricas y las decisiones de selección ya evaluadas.

El texto y la tabla completa para el informe se encuentran en el [anexo de calidad de datos](../../../docs/informe_final/anexo_calidad_datos_38_variables.md).
