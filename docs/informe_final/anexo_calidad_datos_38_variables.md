# Calidad y completitud de las variables analíticas

## Población y procedimiento

El perfil de calidad se calculó sobre las 8.914.963 transacciones etiquetadas de la vista `dbo.vw_dataset_maestro` de `FraudeDB`. La población comprende 13.332 fraudes y 8.901.631 operaciones sin fraude, con una prevalencia de fraude de 0,149546 %. El periodo observado se extiende desde el 1 de enero de 2010 a las 00:01 hasta el 31 de octubre de 2019 a las 23:57.

La ejecución del 13 de septiembre de 2026 empleó la consulta versionada `src/evaluation/sql/01_profile_data_quality.sql`. Se obtuvieron tres resultados: resumen de población, completitud por variable y controles básicos de calidad. El porcentaje de nulos se calculó como el número de filas nulas dividido por 8.914.963 y multiplicado por cien. La lectura no modificó las tablas ni las vistas.

## Completitud de las 38 variables

Las 38 variables disponen de una medición explícita de completitud. Treinta y cuatro presentan cero nulos y cuatro contienen datos faltantes. La tabla utiliza como denominador la totalidad de la vista etiquetada.

| Variable | Filas nulas | Porcentaje nulo |
|---|---:|---:|
| `account_open_month` | 0 | 0,000000 % |
| `account_open_year` | 0 | 0,000000 % |
| `age_at_transaction` | 0 | 0,000000 % |
| `amount` | 0 | 0,000000 % |
| `amount_to_credit_limit` | 35.689 | 0,400327 % |
| `amount_to_yearly_income` | 0 | 0,000000 % |
| `card_account_age_years` | 0 | 0,000000 % |
| `card_brand` | 0 | 0,000000 % |
| `card_id` | 0 | 0,000000 % |
| `card_type` | 0 | 0,000000 % |
| `client_id` | 0 | 0,000000 % |
| `credit_limit` | 0 | 0,000000 % |
| `credit_score` | 0 | 0,000000 % |
| `current_age` | 0 | 0,000000 % |
| `day_of_week` | 0 | 0,000000 % |
| `gender` | 0 | 0,000000 % |
| `has_chip` | 0 | 0,000000 % |
| `is_fraud` | 0 | 0,000000 % |
| `is_weekend` | 0 | 0,000000 % |
| `mcc` | 0 | 0,000000 % |
| `mcc_description` | 0 | 0,000000 % |
| `merchant_city` | 0 | 0,000000 % |
| `merchant_id` | 0 | 0,000000 % |
| `merchant_state` | 1.047.865 | 11,754003 % |
| `merchant_zip` | 1.107.377 | 12,421555 % |
| `months_to_card_expiration` | 0 | 0,000000 % |
| `num_cards_issued` | 0 | 0,000000 % |
| `num_credit_cards` | 0 | 0,000000 % |
| `per_capita_income` | 0 | 0,000000 % |
| `retirement_age` | 0 | 0,000000 % |
| `total_debt` | 0 | 0,000000 % |
| `transaction_date` | 0 | 0,000000 % |
| `transaction_hour` | 0 | 0,000000 % |
| `transaction_id` | 0 | 0,000000 % |
| `transaction_month` | 0 | 0,000000 % |
| `use_chip` | 0 | 0,000000 % |
| `yearly_income` | 0 | 0,000000 % |
| `years_since_pin_change` | 1.293.579 | 14,510200 % |

Los mayores porcentajes de nulos corresponden a `years_since_pin_change` (14,510200 %), `merchant_zip` (12,421555 %) y `merchant_state` (11,754003 %). En `amount_to_credit_limit` se observaron 35.689 nulos (0,400327 %), cantidad coincidente con las filas cuyo límite de crédito es igual o menor que cero. Esta coincidencia de recuentos es coherente con la necesidad de evitar cocientes con límites no válidos; la verificación fila a fila no forma parte de estos tres resultados agregados.

Los identificadores de transacción, cliente, tarjeta y comercio, junto con la fecha de transacción, la descripción MCC y la etiqueta de fraude, presentan cero nulos. Esta medición completa el respaldo de esos siete campos, que no contaban con una tasa de nulos en la tabla histórica de evaluación de candidatos.

## Controles de calidad

| Control | Filas detectadas | Interpretación |
|---|---:|---|
| `cuentas_previas_inconsistentes` | 214 | Cuenta abierta después de la transacción |
| `edades_fuera_rango` | 0 | Edad calculada menor que 0 o mayor que 120 |
| `ingresos_no_positivos` | 0 | Ingreso anual igual o menor que cero |
| `limites_no_positivos` | 35.689 | Límite de crédito igual o menor que cero |
| `montos_cero` | 7.193 | Revisar su significado operativo |
| `montos_negativos` | 442.779 | Revisar como posibles devoluciones; no eliminar automáticamente |
| `puntajes_fuera_rango` | 0 | Puntaje fuera del intervalo 300 a 850 |
| `tarjetas_vencidas` | 60 | Vencimiento anterior a la transacción; requiere revisión |

Los controles detectan condiciones que requieren interpretación según el dominio. Un monto negativo puede corresponder a una devolución y un monto cero requiere aclarar su significado operativo; ninguna condición justifica por sí sola eliminar una transacción. Los recuentos de diferentes controles pueden incluir las mismas filas, por lo que no representan categorías excluyentes.

La ausencia de edades, puntajes e ingresos fuera de los rangos comprobados se limita a esas reglas. Las cuentas abiertas después de la transacción y los vencimientos anteriores constituyen condiciones temporales observadas que deben conservarse en la interpretación de los datos.

## Relación con la selección de variables

El análisis histórico de candidatos se realizó sobre una muestra determinística de 990.261 transacciones con 1.413 fraudes. Esta medición de completitud corresponde a las 8.914.963 transacciones etiquetadas; ambas poblaciones se identifican por separado para evitar mezclar porcentajes. La tabla anterior reemplaza la condición de completitud no medida de los siete campos mencionados, sin atribuirles una evaluación predictiva que no fue realizada.

La presencia de valores completos no demuestra utilidad predictiva. La vista incluye identificadores, variables descriptivas y la etiqueta `is_fraud`, utilizada como objetivo y excluida de las entradas. El modelo oficial conserva sus 22 variables de entrada y las decisiones respaldadas por las comparaciones realizadas. Esta documentación no constituye un nuevo entrenamiento ni una modificación de sus métricas.

## Fuentes de los resultados

- [Resumen de población](../../results/eda/calidad_datos_20260913/01_resumen_general.csv).
- [Completitud de las 38 variables](../../results/eda/calidad_datos_20260913/02_completitud_38_variables.csv).
- [Controles de calidad](../../results/eda/calidad_datos_20260913/03_controles_calidad.csv).
- [Registro de ejecución y huellas de archivos](../../results/eda/calidad_datos_20260913/ejecucion.json).
- [Consulta SQL](../../src/evaluation/sql/01_profile_data_quality.sql) y [diccionario de variables](../../data/reference/data_dictionary.csv).

Los tres CSV conservan sus bytes originales y sus huellas SHA-256 coinciden con el registro de ejecución. La consulta ejecutada coincide con la versión integrada en el commit `546371beadd74b9a85df885f380e9299213d7502`. Los resultados acreditan la medición de completitud y los ocho controles descritos; no sustituyen la evaluación del modelo ni una validación operativa del sistema.
