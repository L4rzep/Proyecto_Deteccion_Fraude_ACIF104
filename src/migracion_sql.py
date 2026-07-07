import pandas as pd
from sqlalchemy import create_engine, text
import urllib
import os

print("--- INICIANDO MIGRACIÓN A SQL SERVER (MODO SEGURO) ---")

# 1. Configuración de conexión 
servidor = r'(localdb)\MSSQLLocalDB' 
base_datos = 'FraudeDB'
driver = 'ODBC Driver 17 for SQL Server'

# Armamos la cadena
params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
cadena_conexion = f"mssql+pyodbc:///?odbc_connect={params}"

engine = create_engine(cadena_conexion)

# ==========================================
# NUEVO: PRUEBA DE CONEXIÓN A LA BASE DE DATOS
# ==========================================
print("\nRealizando prueba de conexión...")
try:
    with engine.connect() as conn:
        # Ejecutamos tu query exactamente como la pediste
        query = text("SELECT id_correcto FROM comprobacion")
        resultado = conn.execute(query).fetchone()
        
        if resultado:
            print(f"✅ ¡ÉXITO! Conexión perfecta. El valor traído es: {resultado[0]}")
        else:
            print("✅ Conexión exitosa, pero la tabla 'comprobacion' está vacía.")
            
except Exception as e:
    print(f"❌ ERROR de conexión o la tabla no existe. Detalle: {e}")
    print("Deteniendo el script. Corrige el error en SQL antes de seguir.")
    exit()  # Esto detiene Python por completo para que no intente la migración
# ==========================================

# 2. Rutas
ruta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_csv = os.path.join(ruta_actual, '..', 'data', 'transactions_data.csv')

# 3. REDUCIMOS EL BLOQUE: 10,000 es digerible para LocalDB
tamaño_bloque = 10000  
contador = 1

print("\nIniciando carga de transacciones. Procesando bloques...")

# 4. Inserción
for chunk in pd.read_csv(ruta_csv, chunksize=tamaño_bloque):
    
    # Limpiamos el monto
    chunk['amount'] = chunk['amount'].str.replace('$', '', regex=False).astype(float)
    
    # Insertamos apuntando a 'transactions_data'
    chunk.to_sql(name='transactions_data', con=engine, if_exists='append', index=False)
    
    print(f"-> Bloque {contador} ({tamaño_bloque} filas) insertado con éxito.")
    contador += 1

print("\n¡MIGRACIÓN COMPLETADA! Eres un crack, revisa tu base de datos.")