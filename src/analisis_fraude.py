import sys
import os
import csv
import time
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine
import urllib
import joblib  # Fundamental para cargar el modelo ya entrenado
import xgboost as xgb


def _resolver_ruta_log():
    """
    Ubica results/monitoring/registro_ejecucion.csv.
    1) Busca la raíz del repo subiendo desde este archivo.
    2) Si no la encuentra (ej: script copiado a la carpeta del build de C#),
       usa la variable de entorno FINAN_LOG_DIR si está definida.
    3) Si tampoco existe, cae a una carpeta 'logs' junto al script.
    """
    aqui = os.path.dirname(os.path.abspath(__file__))

    # Intento 1: subir directorios buscando la carpeta results/monitoring
    candidato = aqui
    for _ in range(5):
        posible = os.path.join(candidato, 'results', 'monitoring')
        if os.path.isdir(posible):
            return os.path.join(posible, 'registro_ejecucion.csv')
        candidato = os.path.dirname(candidato)

    # Intento 2: variable de entorno explícita
    dir_env = os.environ.get('FINAN_LOG_DIR')
    if dir_env:
        os.makedirs(dir_env, exist_ok=True)
        return os.path.join(dir_env, 'registro_ejecucion.csv')

    # Fallback: carpeta logs junto al script (evita que el proceso falle)
    fallback = os.path.join(aqui, 'logs')
    os.makedirs(fallback, exist_ok=True)
    return os.path.join(fallback, 'registro_ejecucion.csv')


def registrar_ejecucion(id_inicio, id_fin, transacciones_procesadas,
                         fraudes_detectados, duracion_segundos,
                         estado, mensaje=""):
    """Agrega una fila al registro histórico de ejecuciones de FINAN."""
    ruta_log = _resolver_ruta_log()
    existe = os.path.isfile(ruta_log)

    try:
        with open(ruta_log, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow([
                    'timestamp', 'id_inicio', 'id_fin',
                    'transacciones_procesadas', 'fraudes_detectados',
                    'duracion_segundos', 'estado', 'mensaje'
                ])
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                id_inicio, id_fin, transacciones_procesadas,
                fraudes_detectados, round(duracion_segundos, 2),
                estado, mensaje
            ])
    except Exception as e:
        # Nunca dejar que un fallo de logging tumbe la inferencia real
        print(f"[ADVERTENCIA] No se pudo escribir el registro de ejecución: {e}")


def ejecutar_inferencia_finan(id_inicio, id_fin):
    """
    Motor de Inferencia FINAN (Modo Producción para C#)
    Este script NO entrena ni genera gráficos. Solo extrae datos nuevos,
    aplica el modelo XGBoost pre-entrenado y guarda los resultados.
    """
    inicio_cronometro = time.time()
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
        mensaje = f"No se encontró el modelo guardado. Detalle: {e}"
        print(f"[ERROR CRÍTICO] {mensaje}")
        registrar_ejecucion(id_inicio, id_fin, 0, 0,
                             time.time() - inicio_cronometro,
                             'ERROR_MODELO', mensaje)
        return

    # 3. Leer SOLO el lote de datos nuevos enviado por C#
    # Asumiendo que C# insertó los datos en una tabla llamada 'transactions_data'
    query = f"SELECT * FROM transactions_data WHERE transaction_id BETWEEN {id_inicio} AND {id_fin}"
    df_nuevos = pd.read_sql(query, con=engine)

    if df_nuevos.empty:
        print("[IA FINAN] No hay registros en este lote para analizar.")
        registrar_ejecucion(id_inicio, id_fin, 0, 0,
                             time.time() - inicio_cronometro,
                             'SIN_DATOS', "No se encontraron transacciones en el rango")
        return

    # Guardamos los IDs originales para poder asociar la predicción al registro correcto
    ids_transacciones = df_nuevos['transaction_id']

    # 4. PREPROCESAMIENTO EXACTO AL DEL ENTRENAMIENTO (Ingeniería de Características)
    # A. Limpieza de caracteres monetarios
    for col in ['amount', 'yearly_income', 'total_debt', 'credit_limit', 'credit_score']:
        if col in df_nuevos.columns:
            df_nuevos[col] = df_nuevos[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)

    # B. Eliminación de variables inútiles (Igual que en el entrenamiento).
    #    Se incluye 'errors' porque es texto libre (ej. 'Insufficient Balance') y el
    #    modelo entrenado no la conoce como feature; dejarla suelta rompe la alineación
    #    de columnas del paso E y puede filtrarse a la predicción como texto crudo.
    #    Se incluyen también columnas de cards_data que son texto/alta cardinalidad:
    #    'card_number', 'cvv', 'expires', 'acct_open_date', 'zip', 'address'.
    columnas_inutiles = ['transaction_id', 'client_id', 'card_id', 'transaction_date', 'merchant_id', 'merchant_city', 'merchant_state', 'errors',
                         'card_number', 'cvv', 'expires', 'acct_open_date', 'zip', 'address']
    df_features = df_nuevos.drop(columns=columnas_inutiles, errors='ignore')

    # B.2 MAPEO DE INDICADORES BINARIOS DE TEXTO A NUMÉRICO
    #     IMPORTANTE: debe ser IDÉNTICO al preprocesamiento usado en el entrenamiento
    #     (analisis_fraude-Full Python.py / fase4_xgboost.py). Si el modelo fue entrenado
    #     con has_chip/card_on_dark_web como 0/1 y aquí no se replica, esta señal se
    #     pierde silenciosamente en producción y el modelo predice con datos incompletos.
    columnas_binarias_si_no = ['has_chip', 'card_on_dark_web']
    for col in columnas_binarias_si_no:
        if col in df_features.columns:
            df_features[col] = (
                df_features[col].astype(str).str.strip().str.upper()
                .map({'YES': 1, 'NO': 0, 'TRUE': 1, 'FALSE': 0, '1': 1, '0': 0})
            )
            df_features[col] = df_features[col].fillna(0).astype(int)

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

    # Ordenamos las columnas exactamente igual a como las espera el modelo.
    # Esto también descarta automáticamente cualquier columna sobrante (ej. texto que
    # se nos haya escapado) que el modelo no conozca, como red de seguridad adicional.
    df_features = df_features[columnas_modelo]

    # 5. PREDICCIÓN (La magia de Machine Learning)
    try:
        print(f"[IA FINAN] Analizando {len(df_features)} transacciones...")
        predicciones = modelo_xgb.predict(df_features)
        probabilidades = modelo_xgb.predict_proba(df_features)[:, 1]  # Extraemos la probabilidad de que sea Fraude (Clase 1)
    except Exception as e:
        mensaje = f"Fallo durante la predicción: {e}"
        print(f"[ERROR CRÍTICO] {mensaje}")
        registrar_ejecucion(id_inicio, id_fin, len(df_features), 0,
                             time.time() - inicio_cronometro,
                             'ERROR_PREDICCION', mensaje)
        return

    # 6. GUARDAR RESULTADOS EN SQL SERVER
    df_resultados = pd.DataFrame({
        'transaction_id': ids_transacciones,
        'is_fraud_predicted': predicciones,
        'fraud_probability': probabilidades
    })

    # Exportamos los resultados a una tabla que C# consultará para mostrar alertas
    try:
        df_resultados.to_sql(name='Resultados_Fraude_FINAN', con=engine, if_exists='append', index=False)
    except Exception as e:
        mensaje = f"Fallo al guardar resultados en SQL: {e}"
        print(f"[ERROR CRÍTICO] {mensaje}")
        registrar_ejecucion(id_inicio, id_fin, len(df_features), int(sum(predicciones)),
                             time.time() - inicio_cronometro,
                             'ERROR_GUARDADO', mensaje)
        return

    total_fraudes = int(sum(predicciones))
    print(f"[IA FINAN] ¡Lote procesado con éxito! Se detectaron {total_fraudes} posibles fraudes.")

    registrar_ejecucion(id_inicio, id_fin, len(df_features), total_fraudes,
                         time.time() - inicio_cronometro, 'OK')


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
