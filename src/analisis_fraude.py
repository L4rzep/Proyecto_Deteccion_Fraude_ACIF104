import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
import urllib
import os
import json
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

print("--- 1. CONECTANDO A SQL SERVER Y EXTRACCIÓN INTELIGENTE ---")
servidor = r'(localdb)\MSSQLLocalDB' 
base_datos = 'FraudeDB'
driver = 'ODBC Driver 17 for SQL Server'
params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
cadena_conexion = f"mssql+pyodbc:///?odbc_connect={params}"
engine = create_engine(cadena_conexion)

query = "SELECT TOP 100000 * FROM transactions_data ORDER BY NEWID()"
df_trx = pd.read_sql(query, con=engine)

# =========================================================================
# 🔥 SOLUCIÓN CRÍTICA: Convertimos el monto de DECIMAL (SQL) a float (Python)
# =========================================================================
df_trx['amount'] = df_trx['amount'].astype(float)
print(f"✅ {len(df_trx)} transacciones extraídas y convertidas a tipo numérico con éxito.")

print("\n--- 2. CARGANDO Y CRUZANDO DIMENSIONES (JOINs) ---")
ruta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_data = os.path.join(ruta_actual, '..', 'data')

df_users = pd.read_csv(os.path.join(ruta_data, 'users_data.csv'))
df_cards = pd.read_csv(os.path.join(ruta_data, 'cards_data.csv'))

with open(os.path.join(ruta_data, 'train_fraud_labels.json'), 'r') as file:
    etiquetas_raw = json.load(file)
etiquetas_dict = etiquetas_raw['target'] if 'target' in etiquetas_raw else etiquetas_raw
df_etiquetas = pd.DataFrame(list(etiquetas_dict.items()), columns=['id', 'es_fraude'])
df_etiquetas['id'] = df_etiquetas['id'].astype(int)
df_etiquetas['es_fraude'] = df_etiquetas['es_fraude'].map({'Yes': 1, 'No': 0})

df_maestro = pd.merge(df_trx, df_cards, left_on='card_id', right_on='id', how='left', suffixes=('_trx', '_card'))
df_maestro = pd.merge(df_maestro, df_users, left_on='client_id_trx', right_on='id', how='left', suffixes=('', '_user'))
df_maestro = pd.merge(df_maestro, df_etiquetas, left_on='id_trx', right_on='id', how='left')

df_maestro['es_fraude'] = df_maestro['es_fraude'].fillna(0).astype(int)

# Aseguramos que credit_limit también sea estrictamente float numérico
if df_maestro['credit_limit'].dtype == object:
    df_maestro['credit_limit'] = df_maestro['credit_limit'].str.replace('$', '', regex=False).astype(float)
else:
    df_maestro['credit_limit'] = df_maestro['credit_limit'].astype(str).str.replace('$', '', regex=False).astype(float)

# Aseguramos que la edad sea numérica
df_maestro['current_age'] = df_maestro['current_age'].astype(float)

print(f"✅ Tabla Maestra consolidada: {df_maestro.shape[0]} filas listas para IA.")

print("\n--- 3. ANÁLISIS EXPLORATORIO (EDA) PARA TU INFORME ---")
# Gráfico 1: Histograma
plt.figure(figsize=(10, 5))
sns.histplot(df_maestro[df_maestro['amount'] < 500]['amount'].dropna(), bins=50, kde=True, color='purple')
plt.title('Distribución de Montos de Transacciones')
plt.xlabel('Monto en Dólares ($)')
plt.ylabel('Frecuencia')
plt.show()

# Gráfico 2: Mapa de Calor (¡Ahora sí se generará sin problemas!)
plt.figure(figsize=(8, 6))
columnas_numericas = ['amount', 'credit_limit', 'current_age', 'es_fraude']
sns.heatmap(df_maestro[columnas_numericas].dropna().corr(), annot=True, cmap='coolwarm', fmt=".2f")
plt.title('Correlación entre Variables Financieras y Fraude')
plt.show()

print("\n--- 4. MODELADO Y BALANCEO DE CLASES (SMOTE) ---")
X = df_maestro[['amount', 'credit_limit', 'current_age']].fillna(0)
y = df_maestro['es_fraude']

X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y)
X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.176, random_state=42, stratify=y_temp)

print(f"Fraudes en Entrenamiento antes de equilibrar: {sum(y_train == 1)}")
smote = SMOTE(random_state=42)
X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)
print(f"Fraudes en Entrenamiento DESPUÉS de equilibrar (SMOTE): {sum(y_train_smote == 1)}")

print("\n--- 5. ENTRENAMIENTO DEL RANDOM FOREST ---")
modelo_rf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
modelo_rf.fit(X_train_smote, y_train_smote)

predicciones_val = modelo_rf.predict(X_val)
print("\n🔥 Reporte de Precisión de la IA (Set de Validación) 🔥")
print(classification_report(y_val, predicciones_val))