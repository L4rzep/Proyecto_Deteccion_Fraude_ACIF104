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

## Comparación de estrategias de balanceo

Con la configuración de variables seleccionada se compararon las tres
estrategias solicitadas en la retroalimentación: datos sin balanceo,
submuestreo aleatorio y SMOTE. Todas utilizaron el mismo conjunto de
entrenamiento, la misma validación y el mismo XGBoost, por lo que la diferencia
entre los resultados corresponde al tratamiento del desbalance.

Para comparar las estrategias se ajustó el umbral solamente con los datos de
validación. El conjunto de prueba continuó reservado.

| Estrategia | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|
| Sin balanceo | 0,6970 | 0,3255 | 0,4437 | 0,9362 | 0,3803 |
| Submuestreo aleatorio | 0,0986 | 0,1651 | 0,1235 | 0,9389 | 0,0543 |
| SMOTE | 0,0815 | 0,2925 | 0,1274 | 0,9305 | 0,0685 |

Se seleccionó el escenario sin balanceo porque presentó el mejor PR-AUC y el
mejor F1 en validación. El submuestreo y SMOTE lograron detectar más fraudes
al utilizar el umbral estándar de 0,5, pero también produjeron muchas más
falsas alarmas. Después de ajustar el umbral de cada alternativa en
validación, ninguna superó al entrenamiento con los datos originales.

Esta elección no significa que el desbalance se haya ignorado. Las tres
alternativas fueron implementadas y medidas bajo las mismas condiciones. En
este conjunto de datos, conservar todos los casos normales entregó más
información útil al modelo que eliminar registros o crear casos sintéticos.

El umbral de 0,1442 pertenece a esta comparación y todavía no es el umbral
definitivo de la aplicación. Primero se deben comparar las técnicas de ML y
las arquitecturas de DL; recién después se seleccionará un modelo y se usará
una sola vez el conjunto de prueba reservado.

### Archivos de evidencia del balanceo

- `balancing_strategy_comparison.csv`: métricas completas de las tres
  estrategias, incluidos los errores y aciertos de cada una.
- `balancing_strategy_comparison.png`: comparación gráfica de sus métricas.
- `balancing_strategy_selected.json`: estrategia seleccionada y regla de
  selección.
- `balancing_strategy_metadata.json`: muestra, división, variables, versiones
  y confirmación de que el conjunto de prueba no fue utilizado.

## Comparación de técnicas de aprendizaje automático

Se compararon las tres técnicas planteadas en los informes formativos:
Regresión Logística, Random Forest y XGBoost. Todas recibieron las mismas
693.182 filas de entrenamiento, las mismas 178 columnas preparadas y los
mismos 148.539 casos de validación. No se aplicó balanceo y el conjunto de
prueba permaneció reservado.

| Modelo | Precisión | Recall | F1 | ROC-AUC | PR-AUC | Entrenamiento |
|---|---:|---:|---:|---:|---:|---:|
| Regresión Logística | 0,1303 | 0,2028 | 0,1587 | 0,9000 | 0,0704 | 251,06 s |
| Random Forest | 0,7500 | 0,4104 | 0,5305 | 0,9224 | 0,4569 | 44,12 s |
| XGBoost | 0,6970 | 0,3255 | 0,4437 | 0,9362 | 0,3803 | 6,03 s |

Random Forest fue seleccionado como el mejor modelo de ML porque obtuvo el
PR-AUC y el F1 más altos. Con el umbral ajustado en validación identificó 87 de
los 212 fraudes, con 29 falsas alarmas. XGBoost fue más rápido y tuvo el mejor
ROC-AUC, pero quedó por debajo de Random Forest en las métricas principales
para esta clase minoritaria.

La precisión, el recall y el F1 de la tabla utilizan el umbral que produjo el
mejor F1 para cada modelo en validación. Esto evita juzgar los modelos solo con
el umbral general de 0,5, que en un problema tan desbalanceado puede ocultar
fraudes. PR-AUC se utilizó como criterio principal porque resume mejor el
equilibrio entre detectar fraudes y evitar falsas alarmas cuando la clase de
interés es muy pequeña.

El umbral de 0,0633 de Random Forest todavía no corresponde a la aplicación.
Primero se compararán las tres arquitecturas de Deep Learning. Después se
confirmará el modelo final y se utilizará una sola vez el conjunto de prueba.

### Archivos de evidencia de ML

- `ml_model_comparison.csv`: métricas, tiempos y matrices de confusión de los
  tres modelos.
- `ml_model_comparison.png`: gráfico comparativo de las métricas principales.
- `ml_model_selected.json`: modelo ML seleccionado y umbral de validación.
- `ml_model_metadata.json`: variables, parámetros, división, versiones y
  confirmación de que el test no fue utilizado.

El siguiente paso es comparar tres arquitecturas de Deep Learning bajo la
misma división y con el conjunto de prueba todavía reservado.
