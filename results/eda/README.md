# Análisis exploratorio de datos

Esta etapa se realizó después de preparar la base `FraudeDB` y crear la vista
`dbo.vw_dataset_maestro`. El propósito fue conocer mejor los datos antes de
entrenar los modelos y dejar evidencia de las decisiones tomadas.

El análisis se dividió en tres partes:

1. revisión general de la cantidad y calidad de los datos;
2. estudio de los montos poco habituales; y
3. generación de tablas y gráficos para comparar fraude y no fraude.

Los archivos utilizados para repetir el análisis se encuentran en
`src/evaluation/`.

## Datos revisados

La base contiene 8.914.963 transacciones con una etiqueta conocida. De ellas,
13.332 corresponden a fraude y 8.901.631 a operaciones sin fraude. Esto
equivale a un 0,149546 % de fraude.

El periodo cubierto va desde el 1 de enero de 2010 hasta el 31 de octubre de
2019. La baja proporción de fraudes confirma que se está trabajando con un
problema muy desbalanceado. Por este motivo, más adelante no bastará con
informar solamente la exactitud del modelo: también se deberán revisar
precisión, recall, F1 y AUC.

## Calidad de los datos

Se revisaron las 38 variables de la vista analítica. La mayoría presenta sus
datos completos. Entre los casos que requieren atención se encontraron 35.689
registros sin una relación válida entre monto y límite de crédito, además de
1.293.579 registros sin información suficiente para calcular los años desde el
último cambio de PIN.

El nombre, tipo, origen y función de cada variable se encuentran en
`data/reference/data_dictionary.csv`. Este archivo permite distinguir los
datos que pueden utilizarse como entrada del modelo, los identificadores, la
etiqueta de fraude y los campos que todavía deben revisarse.

También se encontraron los siguientes casos para revisión:

- 442.779 montos negativos;
- 7.193 transacciones con monto cero;
- 35.689 límites de crédito iguales o menores que cero;
- 214 casos donde la fecha de apertura de la cuenta queda después de la
  transacción; y
- 60 tarjetas cuya fecha de vencimiento queda antes de la transacción.

Estos registros no se eliminaron automáticamente. Por ejemplo, un monto
negativo puede representar una devolución y no necesariamente un error. Cada
caso debe evaluarse según su significado y su posible aporte al modelo.

No se encontraron edades fuera del rango de 0 a 120 años, puntajes de crédito
fuera del intervalo de 300 a 850 ni ingresos anuales iguales o menores que
cero.

## Montos y valores atípicos

Para comparar los montos se utilizó su valor absoluto, ya que las devoluciones
pueden aparecer como valores negativos. Los principales resultados fueron:

- primer cuartil: 11,75;
- mediana: 34,81;
- tercer cuartil: 70,97; y
- límite superior para considerar un monto atípico: 159,80.

Se identificaron 416.825 transacciones fuera de ese límite. En ellas hubo
3.402 fraudes, con una tasa de 0,816170 %. En las 8.498.138 transacciones que
quedaron dentro del rango habitual hubo 9.930 fraudes, equivalentes a
0,116849 %.

En otras palabras, la tasa de fraude de los montos atípicos fue casi siete
veces mayor. Esto indica que el monto puede aportar información útil y también
justifica que los valores altos no se eliminen solo por ser poco frecuentes.

La decisión para la siguiente etapa es conservar todas las transacciones y no
recortar los montos atípicos. Se compararán dos preparaciones: el monto original
y una versión transformada que reduzca el efecto de los valores muy altos sin
perder el signo de las devoluciones. La elección final dependerá del resultado
de los modelos y quedará registrada junto con sus métricas.

El monto promedio también presentó una diferencia: 42,85 en las operaciones
sin fraude y 110,23 en las operaciones fraudulentas. Esta diferencia debe
entenderse como una relación observada en los datos y no como una prueba de que
un monto alto sea necesariamente fraudulento.

## Modalidad de la transacción

La modalidad online presentó la mayor tasa de fraude:

| Modalidad | Transacciones | Fraudes | Porcentaje de fraude |
|---|---:|---:|---:|
| Online | 1.043.975 | 8.779 | 0,840921 % |
| Chip | 3.202.776 | 3.176 | 0,099164 % |
| Banda | 4.668.212 | 1.377 | 0,029497 % |

La diferencia sugiere que `use_chip` puede ser una variable importante para el
modelo. Sin embargo, una operación online no debe clasificarse como fraude por
ese solo hecho.

## Categorías de comercio

También se compararon las categorías MCC. Entre las categorías con mayor
cantidad de fraudes aparecen tiendas por departamento, clubes mayoristas,
tiendas de descuento, transferencias de dinero y farmacias.

El gráfico MCC selecciona las categorías por cantidad de fraudes y muestra la
tasa correspondiente en cada una. Por eso una categoría con muchos casos no es
necesariamente la que tiene el mayor porcentaje. Esta información permitirá
evaluar si el código MCC aporta al modelo sin sacar conclusiones solamente por
el nombre del comercio.

## Evaluación de variables previa al modelamiento

Después del EDA se revisaron 32 variables mediante una muestra determinística
de 990.261 transacciones, con 1.413 fraudes. Esta revisión no entrenó modelos:
comparó la completitud, la cantidad de valores distintos y las diferencias
observadas entre fraude y no fraude. Por ese motivo, sus resultados sirven para
formar los conjuntos candidatos, pero la decisión final debe confirmarse con
las métricas de validación.

El monto presentó la mayor diferencia entre las variables numéricas. Se
mantendrá el valor original y también se probará, como alternativa, una
transformación logarítmica que conserva el signo de las devoluciones. Ambas
versiones no se utilizarán juntas en una misma configuración.

La modalidad de la transacción, el código MCC y la hora mostraron diferencias
claras entre fraude y no fraude. En cambio, `merchant_city`, `merchant_state` y
`merchant_zip` parecían aportar una señal elevada principalmente porque sus
valores `ONLINE` o nulos repiten la información ya expresada por `use_chip`.
Además, ciudad y código postal generan miles de categorías. Por estas razones,
se utilizará `use_chip` y se excluirá la ubicación detallada del conjunto
principal.

`current_age` y `age_at_transaction` entregaron diferencias prácticamente
iguales. Se seleccionó `age_at_transaction`, porque representa la edad del
cliente cuando ocurrió la operación y mantiene mejor la coherencia temporal.
La variable `gender` mostró una diferencia mínima y, además, requiere una
revisión de equidad; por ello no se incorporará al modelo.

Las variables financieras provenientes del perfil del cliente, como ingresos,
deuda, puntaje y límite de crédito, se conservarán en un conjunto ampliado. Se
compararán con el conjunto principal porque todavía debe confirmarse que sus
valores corresponden temporalmente a la fecha de cada transacción.

Para evitar repetir la extracción y el procesamiento, la siguiente etapa
comparará en una sola ejecución cuatro configuraciones:

1. conjunto principal con el monto original;
2. conjunto principal con el monto transformado;
3. conjunto ampliado con el monto original; y
4. conjunto ampliado con el monto transformado.

Las cuatro configuraciones utilizarán la misma división estratificada de 70 %
para entrenamiento, 15 % para validación y 15 % reservado para prueba. La
configuración se escogerá únicamente con validación; el conjunto de prueba no
se utilizará durante esta selección.

## Uso de una muestra para los gráficos de montos

Las cantidades generales, las modalidades y las categorías MCC se calcularon
con las 8.914.963 transacciones etiquetadas. Para dibujar la distribución y el
diagrama de caja de los montos se seleccionaron 990.261 transacciones, de las
cuales 1.413 correspondían a fraude. La proporción de fraude de la muestra fue
0,142690 %, cercana al 0,149546 % observado en el conjunto completo.

La selección toma uno de cada nueve registros de acuerdo con una regla
repetible y la semilla 42. La cantidad exacta y el número de fraudes obtenidos
quedan registrados en `sample_summary.csv` y `eda_run_metadata.json`. Esta
muestra se utiliza solo para facilitar la creación de los dos gráficos de
montos; no reemplaza los datos completos ni define la muestra que se usará para
entrenar los modelos.

## Archivos generados

| Archivo | Contenido |
|---|---|
| `class_distribution.csv` | Cantidad y porcentaje de fraude y no fraude. |
| `class_distribution.png` | Gráfico del desbalance de las clases. |
| `use_chip_summary.csv` | Resultados por modalidad de transacción. |
| `fraud_rate_by_channel.png` | Comparación de la tasa de fraude por modalidad. |
| `top_mcc_summary.csv` | Categorías MCC con mayor cantidad de fraudes. |
| `top_mcc_fraud_rate.png` | Comparación de las tasas en esas categorías. |
| `sample_summary.csv` | Resumen de la muestra usada para los gráficos de montos. |
| `amount_distribution_log.png` | Distribución transformada de la magnitud del monto. |
| `amount_boxplot_by_fraud.png` | Comparación de montos entre fraude y no fraude. |
| `eda_run_metadata.json` | Parámetros utilizados para repetir la ejecución. |
| `feature_candidate_assessment.csv` | Calidad, señal individual y decisión provisional de cada variable. |
| `feature_category_rates.csv` | Cantidad y tasa de fraude de las categorías analizadas. |
| `feature_assessment_metadata.json` | Parámetros utilizados para repetir la evaluación de variables. |

Las capturas de SQL Server y VS Code se mantienen como respaldo interno de la
revisión, pero no forman parte de los resultados oficiales que se propone
publicar en el repositorio.

## Conclusión de esta etapa

El análisis confirma que el conjunto está fuertemente desbalanceado y que el
monto, la modalidad de la transacción y la categoría MCC muestran diferencias
que pueden ser útiles para detectar fraude. También deja identificados los
datos faltantes y los casos que deben revisarse sin eliminarlos de manera
automática.

Estos resultados servirán como base para seleccionar variables, preparar las
pruebas de balanceo y comparar los modelos solicitados en la siguiente etapa.
