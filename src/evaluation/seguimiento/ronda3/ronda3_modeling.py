"""Dos ampliaciones de R2 con las mismas opciones de Random Forest."""
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from comportamiento import FEATURES

NUMERIC = ['amount','age_at_transaction','num_credit_cards','num_cards_issued',
           'card_account_age_years','months_to_card_expiration','years_since_pin_change',
           'credit_limit','per_capita_income','yearly_income','total_debt','credit_score',
           'amount_to_credit_limit','amount_to_yearly_income']
CATEGORICAL = ['transaction_hour','day_of_week','transaction_month','use_chip','mcc',
               'card_brand','card_type','has_chip']
EXCLUDED = ['card_account_age_years','months_to_card_expiration','years_since_pin_change']
CONFIGS = [
    {'name':'rf_actualizado_contexto','reference':'rf_actualizado','revised':False},
    {'name':'rf_revisado_contexto','reference':'rf_variables_revisadas','revised':True},
]


class RevisionFeatures(BaseEstimator,TransformerMixin):
    def __init__(self,enabled=False):self.enabled=enabled
    def fit(self,X,y=None):
        self.feature_names_in_=X.columns.to_numpy();self.n_features_in_=len(X.columns)
        return self
    def transform(self,X):
        out=X.copy()
        if self.enabled:
            out['use_chip']=out.use_chip.replace({'Chip Transaction':'Presencial',
                'Swipe Transaction':'Presencial','Online Transaction':'En linea'})
        return out


def build_model(config,jobs=8):
    nums=[n for n in NUMERIC if not(config['revised'] and n in EXCLUDED)]+FEATURES
    numeric=Pipeline([('imputer',SimpleImputer(strategy='median',keep_empty_features=True)),
                      ('scaler',StandardScaler())])
    categorical=Pipeline([('imputer',SimpleImputer(strategy='most_frequent',keep_empty_features=True)),
                          ('ordinal',OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1))])
    preprocess=ColumnTransformer([('numeric',numeric,nums),('categorical',categorical,CATEGORICAL)])
    onehot=ColumnTransformer([('numeric','passthrough',list(range(len(nums)))),
        ('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=True),
        list(range(len(nums),len(nums)+len(CATEGORICAL))))],sparse_threshold=1.0)
    forest=RandomForestClassifier(n_estimators=200,max_depth=16,min_samples_leaf=2,
        max_features='sqrt',bootstrap=True,random_state=42,n_jobs=jobs,class_weight=None)
    return Pipeline([('revision',RevisionFeatures(config['revised'])),('preprocess',preprocess),
                     ('onehot',onehot),('model',forest)])
