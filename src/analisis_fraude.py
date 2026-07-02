import pandas as pd
import os
import json

print("--- 1. EXTRACCIÓN DE DATOS (ETL) ---")
# Configuramos las rutas relativas asumiendo la estructura de carpetas de GitHub
ruta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_data = os.path.join(ruta_actual, '..', 'data')

# Cargamos los DataFrames en memoria (equivalente a un SELECT * FROM tabla)
print("Cargando archivos CSV y JSON...")
df_users = pd.read_csv(os.path.join(ruta_data, 'users_data.csv'))
df_cards = pd.read_csv(os.path.join(ruta_data, 'cards_data.csv'))

# Cargamos el diccionario JSON de rubros comerciales
with open(os.path.join(ruta_data, 'mcc_codes.json'), 'r') as file:
    mcc_dict = json.load(file)

print(f"Usuarios cargados: {df_users.shape[0]}")
print(f"Tarjetas cargadas: {df_cards.shape[0]}")

print("\n--- 2. TRANSFORMACIÓN Y CRUCE DE DATOS (JOINs) ---")
# Esto es exactamente igual a un LEFT JOIN en SQL:
# SELECT * FROM cards_data c LEFT JOIN users_data u ON c.client_id = u.id
df_maestro = pd.merge(
    left=df_cards, 
    right=df_users, 
    left_on='client_id', 
    right_on='id', 
    how='left',
    suffixes=('_card', '_user') # Por si hay columnas con el mismo nombre
)

print(f"Tabla maestra creada exitosamente con {df_maestro.shape[0]} registros y {df_maestro.shape[1]} columnas.")

print("\n--- 3. LIMPIEZA DE DATOS (DATA CLEANING) ---")
# El límite de crédito viene como texto con un signo '$' (ej. '$24295').
# Usamos regex para quitar el símbolo y convertirlo a número decimal para el algoritmo.
df_maestro['credit_limit'] = df_maestro['credit_limit'].str.replace('$', '', regex=False).astype(float)
print("-> Columna 'credit_limit' limpiada y convertida a formato numérico.")

# Convertimos columnas categóricas simples a números (1 y 0)
df_maestro['has_chip'] = df_maestro['has_chip'].apply(lambda x: 1 if x == 'YES' else 0)
print("-> Columna 'has_chip' binarizada (1 = YES, 0 = NO).")

print("\nVista previa de la tabla lista para el algoritmo:")
print(df_maestro[['client_id', 'card_brand', 'credit_limit', 'has_chip', 'current_age', 'yearly_income']].head())

# ==========================================
# ESPACIO PARA LA FASE 2 DEL PROYECTO
# Aquí agregaremos el merge con 'transactions_data.csv' y 'train_fraud_labels.json'
# una vez que los descarguen, para luego aplicar el Random Forest.
# ==========================================

# ==========================================
# FASE 2: INTEGRACIÓN Y LIMPIEZA FINAL
# ==========================================

print("\n--- 4. LIMPIEZA ADICIONAL DEL MAESTRO ---")
# Limpiamos los ingresos (yearly_income) y la deuda (total_debt) que quedaron con el signo '$'
columnas_dinero = ['yearly_income', 'total_debt']
for col in columnas_dinero:
    if col in df_maestro.columns:
        df_maestro[col] = df_maestro[col].str.replace('$', '', regex=False).astype(float)
        print(f"-> Columna '{col}' limpiada y convertida a número.")

print("\n--- 5. CARGA DE TRANSACCIONES Y CORRECCIÓN DE ETIQUETAS ---")
ruta_transacciones = os.path.join(ruta_data, 'transactions_data.csv')
ruta_etiquetas = os.path.join(ruta_data, 'train_fraud_labels.json')

# Extraemos la muestra para no desbordar el entrenamiento
print("Extrayendo 600,000 transacciones...")
df_transacciones = pd.read_csv(ruta_transacciones)
df_trx_muestra = df_transacciones.sample(n=600000, random_state=42)

# Cargamos y arreglamos el JSON de las etiquetas
with open(ruta_etiquetas, 'r') as file:
    etiquetas_dict = json.load(file)

# Si el JSON viene envuelto en una llave principal (ej. {"target": {...}}), lo desenvolvemos
if len(etiquetas_dict) == 1:
    llave_principal = list(etiquetas_dict.keys())[0]
    etiquetas_dict = etiquetas_dict[llave_principal]

# Ahora sí lo convertimos en tabla
df_etiquetas = pd.DataFrame(list(etiquetas_dict.items()), columns=['id', 'es_fraude'])
df_etiquetas['id'] = df_etiquetas['id'].astype(int) # Aseguramos que el ID sea numérico para el JOIN

print(f"Etiquetas corregidas y cargadas: {df_etiquetas.shape[0]} registros reales.")

print("\n--- 6. EL GRAN JOIN FINAL (DATASET COMPLETO) ---")
# 1er JOIN: Usamos 'inner' para descartar automáticamente las transacciones que no tienen etiqueta (los NaN)
df_trx_etiquetadas = pd.merge(df_trx_muestra, df_etiquetas, on='id', how='inner')

# 2do JOIN: Cruzamos la transacción con el dueño de la tarjeta y su perfil demográfico
df_dataset_final = pd.merge(
    df_trx_etiquetadas, 
    df_maestro, 
    left_on=['client_id', 'card_id'], 
    right_on=['client_id', 'id_card'], 
    how='inner'
)

# Binarizamos la variable objetivo: 'Yes' a 1 (Fraude) y 'No' a 0 (Legítima)
df_dataset_final['es_fraude'] = df_dataset_final['es_fraude'].apply(lambda x: 1 if x == 'Yes' else 0)

# Imprimimos la radiografía final
print(f"¡Dataset final limpio! {df_dataset_final.shape[0]} filas listas para entrenar.")
print("\nDistribución de Fraude (1 = Fraude, 0 = Legítimo):")
print(df_dataset_final['es_fraude'].value_counts(dropna=False))