import pandas as pd
from sqlalchemy import create_engine
import urllib
import os
import json

print("--- INICIANDO MIGRACIÓN MAESTRA A SQL SERVER ---")

# 1. Configuración de conexión
servidor = r'(localdb)\MSSQLLocalDB' 
base_datos = 'FraudeDB'
driver = 'ODBC Driver 17 for SQL Server'
params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
cadena_conexion = f"mssql+pyodbc:///?odbc_connect={params}"
engine = create_engine(cadena_conexion)

ruta_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# 2. Lógica de limpieza universal
def limpiar_df(df):
    for col in df.columns:
        # Si la columna tiene '$', la limpiamos
        if df[col].dtype == object and df[col].astype(str).str.contains(r'\$', regex=True).any():
            df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)
    return df

# 3. Lista de tareas (Nombre Archivo, Nombre Tabla)
tareas = [
    ('transactions_data.csv', 'transactions_data'),
    ('users_data.csv', 'users_data'),
    ('cards_data.csv', 'cards_data')
]

# 4. Ejecución del proceso
for archivo, tabla in tareas:
    ruta = os.path.join(ruta_data, archivo)
    print(f"\nProcesando {archivo}...")
    
    # Leemos en bloques para no saturar la memoria
    for chunk in pd.read_csv(ruta, chunksize=50000):
        chunk = limpiar_df(chunk)
        chunk.to_sql(name=tabla, con=engine, if_exists='append', index=False)
    print(f"✅ Tabla {tabla} cargada exitosamente.")

# 5. Migración especial para los JSON
def cargar_json(nombre_archivo, nombre_tabla, keys):
    ruta = os.path.join(ruta_data, nombre_archivo)
    with open(ruta, 'r') as f:
        data = json.load(f)
    
    # Convertimos JSON a DataFrame
    if nombre_archivo == 'train_fraud_labels.json':
        df = pd.DataFrame(list(data['target'].items()), columns=['transaction_id', 'is_fraud'])
    else: # mcc_codes
        df = pd.DataFrame(list(data.items()), columns=['mcc', 'description'])
        
    df.to_sql(name=nombre_tabla, con=engine, if_exists='replace', index=False)
    print(f"✅ Tabla {nombre_tabla} cargada exitosamente.")

cargar_json('train_fraud_labels.json', 'fraud_labels', None)
cargar_json('mcc_codes.json', 'mcc_codes', None)

print("\n--- ¡MIGRACIÓN MAESTRA COMPLETADA CON ÉXITO! ---")