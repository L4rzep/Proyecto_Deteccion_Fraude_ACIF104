import pandas as pd
import matplotlib.pyplot as plt
import sqlalchemy
import joblib
import os
from sklearn.metrics import precision_score, recall_score, f1_score

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
# 2. Cargar pipeline entrenado
# ============================
pipeline = joblib.load("models/finan_fraud_pipeline.joblib")

# ============================
# 3. Función de validación temporal (últimos 5 años, muestreo automático)
# ============================
def validacion_temporal_muestreo(engine, modelo, fecha_col="transaction_date", umbral=0.07, muestras_por_año=20000):
    años = pd.read_sql("SELECT DISTINCT YEAR(transaction_date) as year FROM vw_dataset_maestro", engine)
    años = sorted(años["year"].unique())

    # Limitar a los últimos 5 años
    años = años[-5:]
    resultados = []

    for i in range(len(años)-1):
        year_train = años[i]
        year_test  = años[i+1]

        print(f"Entrenando hasta {year_train}, validando en {year_test}...")

        # Entrenamiento: muestreo por cada año hasta year_train
        df_train_total = pd.DataFrame()
        for y in [a for a in años if a <= year_train]:
            query_train = f"SELECT * FROM vw_dataset_maestro WHERE YEAR({fecha_col}) = {y}"
            df_year = pd.read_sql(query_train, engine)

            if "is_fraud" not in df_year.columns or df_year["is_fraud"].nunique() < 2:
                print(f"⚠️ Año {y} no tiene datos válidos, se omite.")
                continue

            # Ajuste automático de tamaño de muestra
            df_sample = df_year.groupby("is_fraud", group_keys=False).apply(
                lambda x: x.sample(
                    n=min(len(x), muestras_por_año//2), random_state=42
                )
            ).reset_index(drop=True)

            df_train_total = pd.concat([df_train_total, df_sample])

        if df_train_total.empty or "is_fraud" not in df_train_total.columns:
            print(f"⚠️ No se pudo generar muestra de entrenamiento para {year_train}, se omite.")
            continue

        X_train = df_train_total.drop(columns=["is_fraud"], errors="ignore")
        y_train = df_train_total["is_fraud"]
        modelo.fit(X_train, y_train)

        # Validación: muestreo del año siguiente
        query_test = f"SELECT * FROM vw_dataset_maestro WHERE YEAR({fecha_col}) = {year_test}"
        df_test = pd.read_sql(query_test, engine)

        if "is_fraud" not in df_test.columns or df_test["is_fraud"].nunique() < 2:
            print(f"⚠️ Validación {year_test} no tiene datos válidos, se omite.")
            continue

        df_test_sample = df_test.groupby("is_fraud", group_keys=False).apply(
            lambda x: x.sample(
                n=min(len(x), muestras_por_año//2), random_state=42
            )
        ).reset_index(drop=True)

        if df_test_sample.empty or "is_fraud" not in df_test_sample.columns:
            print(f"⚠️ No se pudo generar muestra de validación para {year_test}, se omite.")
            continue

        X_test = df_test_sample.drop(columns=["is_fraud"], errors="ignore")
        y_test = df_test_sample["is_fraud"]

        proba = modelo.predict_proba(X_test)[:,1]
        y_pred = (proba >= umbral).astype(int)

        prec = precision_score(y_test, y_pred, zero_division=0)
        rec  = recall_score(y_test, y_pred, zero_division=0)
        f1   = f1_score(y_test, y_pred, zero_division=0)

        resultados.append({"Train hasta":year_train, "Test en":year_test,
                           "Precisión":prec, "Recall":rec, "F1":f1})

    df_resultados = pd.DataFrame(resultados)

    # Guardar resultados
    output_dir = "results/models"
    os.makedirs(output_dir, exist_ok=True)
    df_resultados.to_csv(f"{output_dir}/metricas_temporales.csv", index=False)

    # Graficar solo si hay resultados
    if not df_resultados.empty:
        plt.figure(figsize=(10,6))
        plt.plot(df_resultados["Test en"], df_resultados["Recall"], marker="o", label="Recall")
        plt.plot(df_resultados["Test en"], df_resultados["Precisión"], marker="o", label="Precisión")
        plt.plot(df_resultados["Test en"], df_resultados["F1"], marker="o", label="F1")
        plt.xlabel("Año de prueba")
        plt.ylabel("Métrica")
        plt.title("Evolución temporal del modelo (Recall, Precisión, F1)")
        plt.legend()
        plt.grid(True)
        plt.savefig(f"{output_dir}/evolucion_temporal.png")
        plt.show()
        plt.close()
    else:
        print("⚠️ No se generaron resultados de validación temporal. Revisa los datos disponibles.")

    return df_resultados

# ============================
# 4. Ejecutar validación temporal
# ============================
resultados_temporales = validacion_temporal_muestreo(engine, pipeline, umbral=0.07, muestras_por_año=20000)
print("✅ Validación temporal completada. Resultados en results/models/metricas_temporales.csv")
print(resultados_temporales)
