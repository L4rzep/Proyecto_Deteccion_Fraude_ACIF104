import joblib
import pandas as pd
from sqlalchemy import create_engine
import urllib
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

def extraer_datos(limite=1000000):
    """
    Sección 1: Extracción de Datos
    Se conecta al Data Warehouse en SQL Server mediante SQLAlchemy y extrae una 
    muestra aleatoria representativa. Realiza una limpieza inicial de los tipos de datos.
    """
    print(f"--- 1. EXTRACCION DESDE SQL SERVER (Muestra: {limite} registros) ---")
    
    # Configuracion de la cadena de conexion ODBC para SQL Server Local
    servidor = r'(localdb)\MSSQLLocalDB' 
    base_datos = 'FraudeDB'
    driver = 'ODBC Driver 17 for SQL Server'
    params = urllib.parse.quote_plus(f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={base_datos};Trusted_Connection=yes;")
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
    
    # Extraccion aleatoria delegada al motor SQL (ORDER BY NEWID()) para optimizar memoria
    query = f"SELECT TOP {limite} * FROM vw_dataset_maestro ORDER BY NEWID()"
    df = pd.read_sql(query, con=engine)
    
    # Limpieza de caracteres monetarios para transformarlos en variables numericas continuas (float)
    for col in ['amount', 'yearly_income', 'total_debt', 'credit_limit', 'credit_score']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)
            
    print(f"Datos extraidos correctamente. Dimensiones del dataset: {df.shape}")
    return df

def generar_graficos(df):
    """
    Sección 2: Análisis Exploratorio de Datos (EDA)
    Genera visualizaciones estadisticas para identificar distribuciones y 
    correlaciones antes del preprocesamiento.
    """
    print("\n--- 2. GENERANDO ANALISIS EXPLORATORIO (EDA) ---")
    print("Nota: Cierre las ventanas de los graficos secuencialmente para continuar el pipeline.")
    
    # Histograma de distribucion de montos para analizar asimetria y valores atipicos
    plt.figure(figsize=(10, 6))
    sns.histplot(df['amount'].dropna(), bins=50, kde=True, color='purple')
    plt.title('Distribucion de Montos de Transacciones')
    plt.xlabel('Monto en Dolares ($)')
    plt.ylabel('Frecuencia')
    plt.tight_layout()
    plt.show()

    # Mapa de calor (Heatmap) para evaluar multicolinealidad y correlacion lineal con la variable objetivo
    plt.figure(figsize=(10, 6))
    columnas_numericas = ['amount', 'credit_limit', 'yearly_income', 'total_debt', 'current_age', 'is_fraud']
    sns.heatmap(df[columnas_numericas].corr(), annot=True, cmap='coolwarm', fmt=".2f")
    plt.title('Correlacion Lineal entre Variables Numericas y Fraude')
    plt.tight_layout()
    plt.show() 

def preprocesar_datos(df):
    """
    Sección 3: Ingeniería de Características y Reducción de Dimensionalidad
    Limpia el dataset, maneja valores nulos y aplica One-Hot Encoding a variables categoricas.
    """
    print("\n--- 3. INGENIERIA DE CARACTERISTICAS ---")
    
    # Feature Selection: Se eliminan identificadores unicos y variables geograficas de 
    # alta cardinalidad (ej. merchant_city) para evitar la Maldicion de la Dimensionalidad
    columnas_inutiles = ['transaction_id', 'client_id', 'card_id', 'transaction_date', 'merchant_id', 'merchant_city', 'merchant_state']
    df = df.drop(columns=columnas_inutiles, errors='ignore')
    
    # Imputacion basica de valores nulos
    df = df.fillna(0)

    # Transformacion de variables categoricas de baja cardinalidad a representacion binaria (One-Hot Encoding)
    variables_categoricas = ['use_chip', 'gender', 'card_brand', 'card_type', 'mcc_description']
    df_encoded = pd.get_dummies(df, columns=variables_categoricas, drop_first=True)
    
    print(f"Transformacion completada. Columnas resultantes: {df_encoded.shape[1]}")
    return df_encoded

def entrenar_y_evaluar(df_encoded):
    """
    Sección 4: Modelado Predictivo
    Aplica tecnicas de balanceo sintético (SMOTE), entrena un ensamble de arboles (XGBoost)
    y evalua su rendimiento mediante metricas de clasificacion.
    """
    print("\n--- 4. BALANCEO Y APRENDIZAJE DE MAQUINA (XGBOOST) ---")
    
    # Separacion de matriz de caracteristicas (X) y vector objetivo (y)
    X = df_encoded.drop(columns=['is_fraud'])
    y = df_encoded['is_fraud']

    # Particion estratificada del dataset: Train (70%), Validation (15%), Test (15%)
    X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.30, random_state=42, stratify=y)
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.50, random_state=42, stratify=y_temp)

    # Balanceo de Clases: Synthetic Minority Over-sampling Technique (SMOTE)
    print("Aplicando SMOTE para balancear la clase minoritaria en el set de entrenamiento...")
    smote = SMOTE(random_state=42)
    X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)

    # Instanciacion y entrenamiento del modelo Extreme Gradient Boosting
    print("Entrenando modelo XGBoost...")
    modelo_xgb = XGBClassifier(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42, n_jobs=-1)
    modelo_xgb.fit(X_train_smote, y_train_smote)

    # Evaluacion del modelo contra el set de validacion
    print("\n--- EVALUACION FINAL DEL MODELO ---")
    predicciones = modelo_xgb.predict(X_val)
    print(classification_report(y_val, predicciones))
    
    print("\nMatriz de Confusion:")
    print(confusion_matrix(y_val, predicciones))

    # Analisis de interpretabilidad del modelo (Feature Importance)
    print("\nGenerando grafico de Importancia de Variables (Feature Importance)...")
    plt.figure(figsize=(10, 6))
    importancias = pd.Series(modelo_xgb.feature_importances_, index=X.columns)
    importancias.nlargest(10).sort_values().plot(kind='barh', color='teal')
    plt.title('Top 10 Variables de Mayor Impacto Predictivo')
    plt.xlabel('Peso en el Algoritmo (XGBoost Feature Importance)')
    plt.tight_layout()
    plt.show() 

    return modelo_xgb

if __name__ == "__main__":
    # Pipeline de Ejecucion Principal
    
    # 1. Extraccion (Configurado a 1,000,000 de registros)
    datos_crudos = extraer_datos(limite=1000000) 
    
    # 2. Exploracion visual
    generar_graficos(datos_crudos)
    
    # 3. Transformacion
    datos_limpios = preprocesar_datos(datos_crudos)
    
    # 4. Modelado
    modelo_final = entrenar_y_evaluar(datos_limpios)
    
    # 5. Serializacion: Se exporta el modelo entrenado a un archivo binario para despliegues futuros
    joblib.dump(modelo_final, 'Modelo_Fraude_XGBoost.pkl')
    print("\nEl modelo entrenado ha sido serializado y guardado con exito como 'Modelo_Fraude_XGBoost.pkl'.")