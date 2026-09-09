# Artefactos históricos

`Modelo_Fraude_XGBoost.pkl` corresponde a la integración preliminar. No lo utiliza la aplicación actual.

`reentrenamiento_20260907/` conserva el pipeline, esquema y metadatos de entrenamiento que estaban en `main` antes de este cierre. Su SHA-256 es `ad1bfd2ad89194edbbfcadcd64877d05d95235a944ddf19f555e6d4e6a5ae4a6`. No se dispone aquí de una evaluación final ligada a ese hash.

El modelo servido se recuperó de `deb64c1d630b4c97d1318ff9a727dc1e1c377c04`, con SHA-256 `3b7d4d0d0b557dddd4ff13fa2865ac32365efd5377da059a5cb96db1db1ad178`, que coincide con la evaluación S9 y SHAP. La recuperación resuelve identidad y trazabilidad. No afirma que un modelo sea predictivamente peor sin comparar evidencia compatible.

La referencia oficial está en [MODELO_OFICIAL.json](../../models/MODELO_OFICIAL.json). Estos archivos no deben copiarse a la aplicación ni recibir las métricas de otro artefacto.
