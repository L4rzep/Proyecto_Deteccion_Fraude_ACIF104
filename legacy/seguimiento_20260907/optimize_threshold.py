import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt
import sqlalchemy
import os
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score

# ============================
# 1. Conexión a la base de datos FraudeDB
# ============================
connection_string = (
    "mssql+pyodbc:///?odbc_connect="
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "DATABASE=FraudeDB;"
    "Trusted_Connection=yes;"
)
engine = sqlalchemy.create_engine(connection_string)

# ============================
# 2. Cargar el pipeline entrenado
# ============================
pipeline = joblib.load("models/finan_fraud_pipeline.joblib")

# ============================
# 3. Funciones auxiliares de evaluación
# ============================
def costo_total(y_true, y_pred, costo_fp=1, costo_fn=10):
    """Calcula el costo total de FP y FN."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0,1]).ravel()
    return fp * costo_fp + fn * costo_fn

def evaluar_umbral(pipeline, X_val, y_val, umbrales, costo_fp=1, costo_fn=10):
    """Evalúa distintos umbrales y devuelve métricas + costo."""
    proba = pipeline.predict_proba(X_val)[:,1]
    resultados = []
    for t in umbrales:
        y_pred = (proba >= t).astype(int)
        prec = precision_score(y_val, y_pred, zero_division=0)
        rec  = recall_score(y_val, y_pred, zero_division=0)
        f1   = f1_score(y_val, y_pred, zero_division=0)
        costo = costo_total(y_val, y_pred, costo_fp, costo_fn)
        resultados.append((t, prec, rec, f1, costo))
    return pd.DataFrame(resultados, columns=["Umbral","Precisión","Recall","F1","Costo"])

# ============================
# 4. Optimización de umbral (validación 2019 en chunks)
# ============================
query = "SELECT * FROM vw_dataset_maestro WHERE YEAR(transaction_date) = 2019"
chunks = pd.read_sql(query, engine, chunksize=50000)

umbrales = np.linspace(0.01, 0.20, 20)
tabla_final = pd.DataFrame()

for i, chunk in enumerate(chunks):
    print(f"Procesando bloque {i}, filas: {len(chunk)}")
    if "is_fraud" not in chunk.columns:
        print("⚠️ El bloque no contiene columna 'is_fraud', se omite.")
        continue
    X_val, y_val = chunk.drop("is_fraud", axis=1), chunk["is_fraud"]
    X_val = X_val.apply(pd.to_numeric, errors="coerce").fillna(0)
    tabla_chunk = evaluar_umbral(pipeline, X_val, y_val, umbrales)
    tabla_final = pd.concat([tabla_final, tabla_chunk])

if tabla_final.empty:
    print("⚠️ No se generaron resultados de optimización de umbral. Revisa los datos.")
else:
    tabla_resultados = tabla_final.groupby("Umbral").mean().reset_index()

    # ============================
    # 5. Guardar resultados y curva costo-umbral
    # ============================
    output_dir = "results/models"
    os.makedirs(output_dir, exist_ok=True)

    tabla_resultados.to_csv(f"{output_dir}/metricas_umbral.csv", index=False)

    fila_optima = tabla_resultados.loc[tabla_resultados["Costo"].idxmin()]
    umbral_optimo = fila_optima["Umbral"]
    costo_optimo = fila_optima["Costo"]

    plt.figure(figsize=(8,6))
    plt.plot(tabla_resultados["Umbral"], tabla_resultados["Costo"], marker="o", label="Costo total")
    plt.axvline(x=umbral_optimo, color="red", linestyle="--", label=f"Umbral óptimo = {umbral_optimo:.2f}")
    plt.scatter(umbral_optimo, costo_optimo, color="red", s=100, zorder=5)
    plt.text(umbral_optimo+0.005, costo_optimo+50, f"Costo mínimo = {costo_optimo:.2f}", color="red")
    plt.xlabel("Umbral de decisión")
    plt.ylabel("Costo total promedio")
    plt.title("Curva costo-umbral (validación 2019)")
    plt.legend()
    plt.grid(True)
    plt.savefig(f"{output_dir}/curva_costo_umbral_optimo.png")
    plt.show()
    plt.close()

    print(f"✅ Resultados guardados en {output_dir}/metricas_umbral.csv y {output_dir}/curva_costo_umbral_optimo.png")
    print(f"Umbral óptimo: {umbral_optimo:.2f} con costo {costo_optimo:.2f}")
