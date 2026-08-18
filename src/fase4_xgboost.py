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
# 1. Eliminamos IDs, fechas y variables de ALTA CARDINALIDAD que explotan la memoria RAM.
#    Se incluye 'errors' porque es texto libre (ej. 'Insufficient Balance') y no aporta
#    valor si no se codifica explícitamente; de lo contrario revienta en SMOTE/XGBoost.
#    Se incluyen también columnas de cards_data que son texto/alta cardinalidad y no
#    deben usarse como feature directa: 'card_number', 'cvv', 'expires', 'acct_open_date', 'zip'.
columnas_inutiles = [
    'transaction_id', 'client_id', 'card_id', 'transaction_date', 
    'merchant_id', 'merchant_city', 'merchant_state', 'errors',
    'card_number', 'cvv', 'expires', 'acct_open_date', 'zip', 'address'
]
df = df.drop(columns=columnas_inutiles, errors='ignore')

# 1.b MAPEO DE INDICADORES BINARIOS DE TEXTO A NUMÉRICO
#     has_chip y card_on_dark_web vienen como 'Yes'/'No' (varchar) desde cards_data.
#     Son señales potencialmente muy predictivas para fraude, así que se convierten
#     explícitamente a 1/0 ANTES de que caigan en la limpieza de texto genérica,
#     que de otro modo las descartaría por completo.
columnas_binarias_si_no = ['has_chip', 'card_on_dark_web']
for col in columnas_binarias_si_no:
    if col in df.columns:
        df[col] = (
            df[col].astype(str).str.strip().str.upper()
            .map({'YES': 1, 'NO': 0, 'TRUE': 1, 'FALSE': 0, '1': 1, '0': 0})
        )
        # Si algún valor no calzó con el mapeo (nulo, formato inesperado), se asume 0
        # de forma conservadora en vez de dejarlo como texto o NaN.
        df[col] = df[col].fillna(0).astype(int)

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

# 6. Verificación de seguridad: cualquier columna de texto que haya quedado sin codificar
#    se elimina aquí para evitar que SMOTE/XGBoost fallen más adelante con un error
#    críptico como "could not convert string to float".
columnas_texto_restantes = df_encoded.select_dtypes(include='object').columns.tolist()
if columnas_texto_restantes:
    print(f"⚠️ Columnas de texto sin convertir detectadas y eliminadas: {columnas_texto_restantes}")
    df_encoded = df_encoded.drop(columns=columnas_texto_restantes)

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
