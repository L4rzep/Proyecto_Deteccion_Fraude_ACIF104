# Requisitos y verificación

FINAN es una aplicación académica de consulta y apoyo a revisión. Los objetivos de latencia y capacidad son propuestas explícitas; no representan acuerdos de nivel de servicio de un banco.

| Requisito | Comprobación | Evidencia y límite |
|---|---|---|
| Consulta y predicción | Caso existente y nuevo; no insertar en tablas fuente | Evidencia manual S9 en `results/app/VALIDACION_APLICACION.md` |
| Usabilidad | Configuración, mensajes y factores legibles | Interfaz S9; no se realizó estudio formal de usuarios |
| Explicabilidad | SHAP global/local y cinco factores finitos en predictor | `results/shap`; integración automática con caso sintético |
| Escalabilidad | P95 propuesto ≤15 s; concurrencia 1, 2 y 4 | 36 solicitudes Python con SHAP; no incluye SQL/WinForms |
| Seguridad | Contrato sin etiqueta ni identificadores sensibles; credenciales locales | Esquema, selección de columnas y logs sin IDs personales |
| Confiabilidad | Rechazar entrada incompleta/no finita y no emitir predicción en error | Casos negativos automatizados |
| Trazabilidad | Modelo, esquema, evaluación y SHAP con identidad compatible | Prueba de hash y archivo oficial; guardia de entrenamiento |
| Monitoreabilidad | Fecha, duración, origen, resultado, versión y errores | JSONL operativo; no mide recall real sin etiquetas posteriores |

## Pruebas del predictor

```powershell
& .\.venv-inferencia\Scripts\python.exe -m unittest discover -s tests -v
```

Diez pruebas aprobadas el 9 de septiembre de 2026. Incluyen contrato, hash, estructura, umbral, invocación del proceso real y SHAP; rechazo de amount ausente/infinito; admisión de categoría desconocida y credit_score nulo; protección del modelo contra sobrescritura antes de consultar SQL. El fixture es sintético. No se calcula otra vez el rendimiento del test S9.

## Microprueba de carga

```powershell
& .\.venv-inferencia\Scripts\python.exe tests/load_backend.py --output data/experimentos/carga_backend.json --requests 12
```

La salida debe ser nueva. [Resultado registrado](../results/app/carga_backend_20260909.json):

| Concurrencia | Solicitudes | P95 (s) | Errores | Solicitudes/s |
|---|---:|---:|---:|---:|
| 1 | 12 | 2,058 | 0 | 0,561 |
| 2 | 12 | 2,592 | 0 | 0,893 |
| 4 | 12 | 2,549 | 0 | 1,741 |

Linux/Python 3.12.13, scikit-learn 1.9.0, artefacto S9 y SHAP, nuevo proceso por petición. Cero timeouts en 36 solicitudes. El generador limita cada ejecución a 60 s; no afirma que la interfaz C# ya implemente ese timeout. La primera serie compartió brevemente el entorno con las pruebas automáticas. Es una medición descriptiva, no una certificación de carga máxima.

La disponibilidad continua no se midió. La compilación y los casos Windows/SQL tienen evidencia histórica S9 y no se repitieron en este entorno Linux. Se requiere comprobar el paquete final en Windows para cerrar la prueba de extremo a extremo.

## Verificación de resultados económicos

`src/evaluation/seguimiento/costos/verificar_costos.py` recalcula decisiones desde las predicciones originales. Aprobó cuatro reglas de negocio y comprobó 81 archivos, 39 curvas, 1.878.142 puntos, 225 decisiones, 135 escenarios y 60 selecciones de frontera. No entrena ni abre el test S9. El resultado está en `results/models/seguimiento/costos/verificacion.json`.

Estas comprobaciones verifican código y coherencia de resultados. No prueban costos reales, ausencia de deriva, calibración, equidad entre segmentos ni rentabilidad futura.
