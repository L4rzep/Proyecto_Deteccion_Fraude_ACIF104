"""Configuraciones predefinidas de la segunda ronda de FINAN."""
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

NUMERIC = ["amount", "age_at_transaction", "num_credit_cards", "num_cards_issued",
           "card_account_age_years", "months_to_card_expiration", "years_since_pin_change",
           "credit_limit", "per_capita_income", "yearly_income", "total_debt", "credit_score",
           "amount_to_credit_limit", "amount_to_yearly_income"]
CATEGORICAL = ["transaction_hour", "day_of_week", "transaction_month", "use_chip", "mcc",
               "card_brand", "card_type", "has_chip"]
REVISED_EXCLUSIONS = ["card_account_age_years", "months_to_card_expiration", "years_since_pin_change"]
CONFIGS = [
    {"name":"rf_actualizado", "recent_years":None, "max_depth":16, "min_samples_leaf":2, "fraud_weight":1, "revised":False},
    {"name":"rf_reciente_3a", "recent_years":3, "max_depth":16, "min_samples_leaf":2, "fraud_weight":1, "revised":False},
    {"name":"rf_profundo", "recent_years":None, "max_depth":None, "min_samples_leaf":1, "fraud_weight":1, "revised":False},
    {"name":"rf_reciente_profundo", "recent_years":3, "max_depth":None, "min_samples_leaf":1, "fraud_weight":1, "revised":False},
    {"name":"rf_peso10_reciente", "recent_years":3, "max_depth":24, "min_samples_leaf":2, "fraud_weight":10, "revised":False},
    {"name":"rf_variables_revisadas", "recent_years":None, "max_depth":16, "min_samples_leaf":2, "fraud_weight":1, "revised":True},
    {"name":"rf_revisado_reciente", "recent_years":3, "max_depth":24, "min_samples_leaf":2, "fraud_weight":10, "revised":True},
]


class RevisionFeatures(BaseEstimator, TransformerMixin):
    """Agrupa explícitamente chip/banda como presencial; conserva otras etiquetas."""
    def __init__(self, enabled=False):
        self.enabled = enabled

    def fit(self, X, y=None):
        self.feature_names_in_ = X.columns.to_numpy()
        self.n_features_in_ = len(X.columns)
        return self

    def transform(self, X):
        result = X.copy()
        if self.enabled:
            result["use_chip"] = result.use_chip.replace({"Chip Transaction":"Presencial",
                                                         "Swipe Transaction":"Presencial",
                                                         "Online Transaction":"En linea"})
        return result


def build_model(config, jobs=8, trees=200):
    numeric_names = [x for x in NUMERIC if not(config["revised"] and x in REVISED_EXCLUSIONS)]
    numeric = Pipeline([("imputer",SimpleImputer(strategy="median",keep_empty_features=True)),
                        ("scaler",StandardScaler())])
    categorical = Pipeline([("imputer",SimpleImputer(strategy="most_frequent",keep_empty_features=True)),
                            ("ordinal",OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1))])
    pre = ColumnTransformer([("numeric",numeric,numeric_names),("categorical",categorical,CATEGORICAL)])
    nc = len(numeric_names)
    onehot = ColumnTransformer([("numeric","passthrough",list(range(nc))),
                                ("categorical",OneHotEncoder(handle_unknown="ignore",sparse_output=True),
                                 list(range(nc,nc+len(CATEGORICAL))))],sparse_threshold=1.0)
    rf = RandomForestClassifier(n_estimators=trees,max_depth=config["max_depth"],
                                min_samples_leaf=config["min_samples_leaf"],max_features="sqrt",
                                bootstrap=True,random_state=42,n_jobs=jobs,
                                class_weight=None if config["fraud_weight"]==1 else {0:1,1:config["fraud_weight"]})
    return Pipeline([("revision",RevisionFeatures(config["revised"])),("preprocess",pre),
                     ("onehot",onehot),("model",rf)])
