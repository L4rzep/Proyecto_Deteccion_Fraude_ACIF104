# Selección de la configuración de variables

Esta etapa comparó los conjuntos de variables definidos después del EDA. Su
objetivo fue escoger una preparación común antes de realizar la comparación
formal de modelos y de técnicas de balanceo.

Los datos se extrajeron una sola vez desde `dbo.vw_dataset_maestro`. Se utilizó
la misma muestra determinística del EDA, formada por 990.261 transacciones y
1.413 fraudes. Luego se realizó una división estratificada con semilla 42:

- entrenamiento: 693.182 transacciones y 989 fraudes;
- validación: 148.539 transacciones y 212 fraudes; y
- prueba reservada: 148.540 transacciones y 212 fraudes.

El conjunto de prueba fue separado y contabilizado, pero no fue transformado,
predicho ni utilizado para escoger variables.

## Configuraciones comparadas

Se compararon dos conjuntos de variables y dos tratamientos del monto. Para
que la comparación fuera equivalente, las cuatro configuraciones utilizaron
el mismo XGBoost de revisión, con ponderación de clase y los mismos datos de
entrenamiento y validación. Este modelo se utilizó solamente para seleccionar
la preparación; no reemplaza los experimentos finales de balanceo.

| Configuración | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|
| Principal, monto original | 0,1551 | 0,2217 | 0,1825 | 0,9420 | 0,0962 |
| Principal, monto transformado | 0,1551 | 0,2217 | 0,1825 | 0,9420 | 0,0962 |
| Ampliado, monto original | 0,1786 | 0,2830 | 0,2190 | 0,9445 | 0,1470 |
| Ampliado, monto transformado | 0,1786 | 0,2830 | 0,2190 | 0,9445 | 0,1470 |

El conjunto ampliado mejoró todas las métricas frente al conjunto principal:
aproximadamente 53 % en PR-AUC, 20 % en F1, 28 % en recall y 15 % en precisión.
Por este motivo, se seleccionó para la etapa siguiente.

El monto original y su transformación logarítmica produjeron exactamente los
mismos resultados en XGBoost. Esto es esperable porque la transformación
conserva el orden de los montos y los árboles separan los datos mediante
puntos de corte. Se mantendrá el monto original para simplificar la
reproducción y la integración con la aplicación. Los modelos que necesiten
escalamiento aplicarán su propio preprocesamiento dentro del pipeline.

## Configuración seleccionada

La configuración seleccionada es `extended_amount_raw`. Incluye variables de
la transacción, tiempo, modalidad, MCC, edad en la fecha de la compra,
características de la tarjeta y variables financieras del perfil.

Las variables financieras mejoraron la validación, pero la fuente no entrega
un historial de sus cambios. El proyecto asume que estos datos están
disponibles al evaluar una nueva transacción y registrará como limitación que
los valores históricos pueden corresponder a una fotografía del perfil. No se
utilizan identificadores, género, ubicación detallada, fecha completa ni la
etiqueta de fraude como entradas del modelo.

El umbral registrado en esta prueba fue escogido únicamente para comparar las
configuraciones en validación. No es todavía el umbral definitivo de FINAN y no
debe copiarse a la aplicación hasta completar la comparación de modelos,
balanceos y evaluación final.

## Archivos de evidencia

- `feature_configuration_comparison.csv`: métricas de las cuatro
  configuraciones.
- `feature_configuration_selected.json`: variables y configuración escogidas.
- `feature_configuration_metadata.json`: muestra, división, política del test
  y versiones utilizadas.

El siguiente paso es utilizar esta única configuración para comparar los
escenarios sin balanceo, submuestreo y SMOTE bajo las mismas condiciones.
