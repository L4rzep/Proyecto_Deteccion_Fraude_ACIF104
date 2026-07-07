import pandas as pd
from sqlalchemy import create_engine
import urllib
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

print("--- 1. EXTRACCIÓN DESDE EL DATA WAREHOUSE ---")
servidor = r'(localdb)\MSSQLLocalDB' 
base_datos = 'FraudeDB'
driver = 'ODBC Driver 17 for SQL Server'
params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
cadena_conexion = f"mssql+pyodbc:///?odbc_connect={params}"
engine = create_engine(cadena_conexion)

# Traemos 150,000 registros al azar de la vista ya cruzada
query = "SELECT TOP 150000 * FROM vw_dataset_maestro ORDER BY NEWID()"
df = pd.read_sql(query, con=engine)
print(f"✅ Dataset extraído: {df.shape[0]} filas y {df.shape[1]} columnas.")

print("\n--- 2. INGENIERÍA DE CARACTERÍSTICAS (PREPROCESAMIENTO) ---")
# 1. Eliminamos IDs, fechas y variables de ALTA CARDINALIDAD que explotan la memoria RAM
columnas_inutiles = [
    'transaction_id', 'client_id', 'card_id', 'transaction_date', 
    'merchant_id', 'merchant_city', 'merchant_state' # <- Las movimos aquí para salvar tu RAM
]
df = df.drop(columns=columnas_inutiles, errors='ignore')

# 2. PARCHE FUERZA BRUTA: Limpiamos el dinero
columnas_dinero = ['amount', 'yearly_income', 'total_debt', 'credit_limit']
for col in columnas_dinero:
    if col in df.columns:
        df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)

# 3. Llenamos nulos
df = df.fillna(0)

# 4. Variables categóricas (Solo las de baja cardinalidad)
variables_categoricas = [
    'use_chip', 'gender', 'card_brand', 'card_type', 'mcc_description'
]

# 5. Transformamos el texto
df_encoded = pd.get_dummies(df, columns=variables_categoricas, drop_first=True)
print(f"✅ Transformación lista. El dataset ahora tiene {df_encoded.shape[1]} columnas numéricas.")

print("\n--- 3. PARTICIÓN DE DATOS Y BALANCEO (SMOTE) ---")
# Separar variables predictoras (X) de la etiqueta (y)
X = df_encoded.drop(columns=['is_fraud'])
y = df_encoded['is_fraud']

# Dividir en Entrenamiento (70%) y Validación/Test (30%)
X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.30, random_state=42, stratify=y)
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.50, random_state=42, stratify=y_temp)

print(f"Fraudes antes de SMOTE: {sum(y_train == 1)}")
smote = SMOTE(random_state=42)
X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)
print(f"Fraudes DESPUÉS de SMOTE: {sum(y_train_smote == 1)}")

print("\n--- 4. ENTRENAMIENTO DEL MODELO XGBOOST ---")
# XGBoost es mucho más potente para detectar fraudes ocultos
modelo_xgb = XGBClassifier(
    n_estimators=100, 
    learning_rate=0.1, 
    max_depth=5, 
    random_state=42, 
    n_jobs=-1,
    eval_metric='logloss'
)

modelo_xgb.fit(X_train_smote, y_train_smote)

print("\n🔥 Reporte de Precisión (XGBoost - Set de Validación) 🔥")
predicciones_val = modelo_xgb.predict(X_val)
print(classification_report(y_val, predicciones_val))