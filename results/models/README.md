# Modelamiento y evidencia de FINAN

Esta carpeta conserva las etapas históricas y la evaluación final S9. Los `*_selected.json` anteriores al refinamiento son decisiones intermedias; sus umbrales no deben copiarse a la aplicación. La identidad vigente está en [MODELO_OFICIAL.json](../../models/MODELO_OFICIAL.json).

## Comparaciones históricas

Las comparaciones S9 utilizaron 990.261 filas, semilla 42 y partición estratificada: 693.182 entrenamiento, 148.539 validación y 148.540 test. El test permaneció reservado durante selección y refinamiento.

| Etapa | Resultado y evidencia |
|---|---|
| Cuatro configuraciones de variables | `extended_amount_raw`; [tabla](feature_configuration_comparison.csv), [metadatos](feature_configuration_metadata.json). Los perfiles financieros son fotografías, no historiales demostrados. |
| Balanceo inicial con XGBoost | Sin balanceo superó submuestreo y SMOTE en PR-AUC/F1; [tabla](balancing_strategy_comparison.csv). Sin balanceo es referencia, no una tercera técnica. |
| Tres técnicas ML | [Tabla](ml_model_comparison.csv), [metadatos](ml_model_metadata.json). RF elegido por PR-AUC y métricas de positivos; XGBoost fue más rápido y obtuvo mayor ROC-AUC. |
| Tres MLP | [Tabla](dl_architecture_comparison.csv), [historia por época](dl_training_history.csv), [parámetros y GPU](dl_architecture_metadata.json). La básica fue la mejor MLP; no superó RF. |
| Comparación ML/DL | [Candidatos finales](final_candidate_comparison.csv). |
| Refinamiento RF | [Tabla](rf_refinement_comparison.csv): 200 árboles/profundidad 16, PR-AUC de validación 0,5014, F1 0,5731. |
| Entrenamiento final | Train + validación, 841.721 filas; [metadatos](final_model_training_metadata.json). |
| Test único | [Métricas](final_test_metrics.json), [matriz](final_confusion_matrix.png), [PR](final_pr_curve.png), [metadatos](final_test_evaluation_metadata.json). |

| Modelo S9 en validación | Precisión | Recall | F1 | PR-AUC | Ajuste (s) |
|---|---:|---:|---:|---:|---:|
| Regresión Logística | 0,1303 | 0,2028 | 0,1587 | 0,0704 | 251,06 |
| RF inicial | 0,7500 | 0,4104 | 0,5305 | 0,4569 | 44,12 |
| XGBoost | 0,6970 | 0,3255 | 0,4437 | 0,3803 | 6,03 |
| MLP 64 | 0,2990 | 0,2877 | 0,2933 | 0,1657 | 281,56 |
| MLP 128–64–32 | 0,0718 | 0,2170 | 0,1079 | 0,0503 | 160,86 |
| MLP 256–128–64 | 0,1730 | 0,2594 | 0,2075 | 0,1290 | 299,58 |

Las redes emplearon ReLU, Adam y sigmoide binaria, hasta 15 épocas y restauración del mejor estado por PR-AUC. Mejores épocas: 15, 5 y 9. Se ejecutaron en GTX 970M/CUDA; sus tiempos no equivalen a los del entorno Linux de seguimiento. El bosque no tiene capas neuronales: se refinó número/profundidad de árboles según la evidencia.

## Resultado oficial S9

Umbral `0.07217143`, TP 87, FP 31, FN 125, TN 148.297. Precisión 73,73 %, recall 41,04 %, F1 52,73 %, PR-AUC 0,478198 y ROC-AUC 0,939748. La limitación principal es omitir 125 de 212 fraudes.

SHA-256 del pipeline: `3b7d4d0d0b557dddd4ff13fa2865ac32365efd5377da059a5cb96db1db1ad178`. Las huellas históricas de JSON se calcularon con finales de línea Windows CRLF; las pruebas aceptan exclusivamente esa normalización al verificarlas. La huella del binario debe coincidir exactamente.

## Seguimiento

En [seguimiento](seguimiento/README.md) se documentan tres estrategias reales frente al desbalance, costos, capacidad, validación temporal, comportamiento e Isolation Forest. Se conserva el test S9 fuera de todos los ensayos. Es desarrollo retrospectivo previamente explorado, no un nuevo test final independiente.

Los scripts y gráficos de septiembre anteriores al estudio consolidado se preservan en [legacy/seguimiento_20260907](../../legacy/seguimiento_20260907/README.md). La aplicación continúa vinculada al artefacto S9; los umbrales temporales se aplican solo a los modelos y ventanas de sus protocolos.
