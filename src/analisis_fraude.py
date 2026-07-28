import sys
import pandas as pd
from sqlalchemy import create_engine
import urllib
import joblib  # Fundamental para cargar el modelo ya entrenado
import xgboost as xgb

def ejecutar_inferencia_finan(id_inicio, id_fin):
    """
    Motor de Inferencia FINAN (Modo Producción para C#)
    Este script NO entrena ni genera gráficos. Solo extrae datos nuevos,
    aplica el modelo XGBoost pre-entrenado y guarda los resultados.
    """
    print(f"[IA FINAN] Iniciando análisis de fraude para IDs del {id_inicio} al {id_fin}...")

    # 1. Configuración de la conexión a SQL Server
    servidor = r'(localdb)\MSSQLLocalDB' 
    base_datos = 'FraudeDB'
    driver = 'ODBC Driver 17 for SQL Server'
    params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    # 2. Cargar el modelo ya entrenado desde el disco
    try:
        # IMPORTANTE: El archivo .pkl debe estar en la misma carpeta que este script
        modelo_xgb = joblib.load('Modelo_Fraude_XGBoost.pkl') 
        print("[IA FINAN] Modelo XGBoost cargado exitosamente en memoria.")
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se encontró el modelo guardado. Detalle: {e}")
        return

    # 3. Leer SOLO el lote de datos nuevos enviado por C#
    # Asumiendo que C# insertó los datos en una tabla llamada 'transactions_data'
    query = f"SELECT * FROM transactions_data WHERE transaction_id BETWEEN {id_inicio} AND {id_fin}"
    df_nuevos = pd.read_sql(query, con=engine)

    if df_nuevos.empty:
        print("[IA FINAN] No hay registros en este lote para analizar.")
        return

    # Guardamos los IDs originales para poder asociar la predicción al registro correcto
    ids_transacciones = df_nuevos['transaction_id']

    # 4. PREPROCESAMIENTO EXACTO AL DEL ENTRENAMIENTO (Ingeniería de Características)
    # A. Limpieza de caracteres monetarios
    for col in ['amount', 'yearly_income', 'total_debt', 'credit_limit', 'credit_score']:
        if col in df_nuevos.columns:
            df_nuevos[col] = df_nuevos[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)
            
    # B. Eliminación de variables inútiles (Igual que en tu código original)
    columnas_inutiles = ['transaction_id', 'client_id', 'card_id', 'transaction_date', 'merchant_id', 'merchant_city', 'merchant_state']
    df_features = df_nuevos.drop(columns=columnas_inutiles, errors='ignore')

    # C. Imputación de nulos
    df_features = df_features.fillna(0)

    # D. Transformación de variables categóricas (One-Hot Encoding)
    variables_categoricas = ['use_chip', 'gender', 'card_brand', 'card_type', 'mcc_description']
    # Solo aplicamos dummies a las columnas que realmente existan en el dataframe
    cols_cat_existentes = [col for col in variables_categoricas if col in df_features.columns]
    df_features = pd.get_dummies(df_features, columns=cols_cat_existentes, drop_first=True)

    # E. ALINEACIÓN DE COLUMNAS (El paso más crítico en producción)
    # Al hacer get_dummies en datos nuevos, pueden faltar columnas que el modelo sí vio en el entrenamiento.
    # Aquí forzamos a que df_features tenga exactamente la misma estructura que el modelo espera.
    columnas_modelo = modelo_xgb.get_booster().feature_names
    for col in columnas_modelo:
        if col not in df_features.columns:
            df_features[col] = 0  # Llenamos con 0 las categorías que no aparecieron en este lote
            
    # Ordenamos las columnas exactamente igual a como las espera el modelo
    df_features = df_features[columnas_modelo] 

    # 5. PREDICCIÓN (La magia de Machine Learning)
    print(f"[IA FINAN] Analizando {len(df_features)} transacciones...")
    predicciones = modelo_xgb.predict(df_features)
    probabilidades = modelo_xgb.predict_proba(df_features)[:, 1] # Extraemos la probabilidad de que sea Fraude (Clase 1)

    # 6. GUARDAR RESULTADOS EN SQL SERVER
    df_resultados = pd.DataFrame({
        'transaction_id': ids_transacciones,
        'is_fraud_predicted': predicciones,
        'fraud_probability': probabilidades
    })

    # Exportamos los resultados a una tabla que C# consultará para mostrar alertas
    df_resultados.to_sql(name='Resultados_Fraude_FINAN', con=engine, if_exists='append', index=False)
    
    total_fraudes = sum(predicciones)
    print(f"[IA FINAN] ¡Lote procesado con éxito! Se detectaron {total_fraudes} posibles fraudes.")

if __name__ == "__main__":
    # C# invocará este script pasando argumentos a través de la consola
    # Ejemplo de lo que C# hace por detrás: python analisis_fraude.py 1 1000
    if len(sys.argv) == 3:
        try:
            id_in = int(sys.argv[1])
            id_fi = int(sys.argv[2])
            ejecutar_inferencia_finan(id_in, id_fi)
        except ValueError:
            print("[ERROR CRÍTICO] Los parámetros enviados por C# no son numéricos válidos.")
    else:
        # Bloque de prueba por si ejecutas el script manualmente desde tu IDE
        print("[MODO DESARROLLADOR] Ejecutando un lote de prueba estático...")
        ejecutar_inferencia_finan(1, 1000)