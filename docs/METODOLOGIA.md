# Metodología y evolución de FINAN

El desarrollo incremental se organiza mediante las seis fases de CRISP-DM. El seguimiento itera desde los hallazgos de evaluación hacia objetivos de negocio, datos y modelamiento.

| Fase | Aplicación | Evidencia |
|---|---|---|
| Comprensión del negocio | Alertas para revisión humana, costo de omisiones y carga de revisión | Alcance en README y protocolo económico |
| Comprensión de datos | Desbalance, cobertura de etiquetas, atípicos, categorías y fechas | `results/eda`, diccionario |
| Preparación | SQL, vistas, imputación, codificación y particiones | `src/data`, esquema del modelo |
| Modelamiento | Tres ML, tres MLP, RF refinado, balanceos y anomalías | `src/models`, `src/evaluation/seguimiento` |
| Evaluación | Test S9 único; seguimiento temporal con decisiones de validación | Metadatos, curvas, matrices y verificadores |
| Despliegue académico | C#–Python–SQL, SHAP, configuración y monitoreo | `app/Finan`, predictor, pruebas |

## Iteraciones

El ciclo S9 seleccionó y refinó RF con PR-AUC y métricas de positivos, fijó el umbral y evaluó el test una vez. El bajo recall llevó a explicitar costos y capacidades, comparar tres estrategias reales de desbalance y evaluar ventanas futuras. Las rondas siguientes revisaron historia reciente, variables y contexto. Isolation Forest comprobó una alternativa no supervisada. Las comparaciones no justificaron una promoción automática.

El test S9 no se reutiliza. El seguimiento usa desarrollo histórico previamente explorado: cumple separación temporal dentro de cada experimento, pero no constituye un nuevo test independiente. Un futuro periodo independiente es necesario para acreditar mejoras de generalización.

## Planificación histórica documentada

| Etapa | Responsable principal S9 | Plazo | Objetivo |
|---|---|---|---|
| Datos, vistas y EDA | Nelson / Juan | Semanas 2–5 | Calidad y reproducibilidad |
| ML y balanceo | Nelson | Semanas 5–7 | Comparación y selección |
| DL | Nelson | Semanas 7–8 | Arquitectura y hardware |
| Aplicación e integración | Rubén | Semanas 4–9 | Consulta e inferencia |
| Repositorio e informe | Juan | Semanas 2–9 | Trazabilidad |
| QA y revisión formal | Sebastián / equipo | Semana 9 | Confiabilidad de entrega |

Esta asignación procede del informe S9; no atribuye retroactivamente tareas posteriores. Los protocolos registran las ejecuciones del seguimiento del 8–9 de septiembre de 2026. La revisión Windows/SQL del paquete final y la integración de la rama se mantienen como pasos de cierre, sin declararlos completados antes de su comprobación.

## Aplicabilidad y mejoras

El sistema apoya revisión académica; no bloquea pagos ni decide sobre personas reales. El score y SHAP describen el modelo, no probabilidades calibradas en producción ni causas.

Las mejoras prioritarias son obtener etiquetas recientes y perfiles válidos a la fecha de transacción, validar costos/capacidad con la organización y medir desempeño diferido y latencia de extremo a extremo. Cada mejora debe demostrar beneficio en costo y carga mensual, con una decisión fijada antes de consultar un nuevo periodo de prueba.
