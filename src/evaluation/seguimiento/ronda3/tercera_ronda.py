"""Seis entrenamientos con contexto previo; comparación retrospectiva con R2.

FINAN_EXPERIMENT_DIR identifica las salidas locales de las rondas anteriores.
No modifica insumos, repositorio ni modelos de entregas anteriores.
"""
from pathlib import Path
from datetime import datetime,timezone
import os
import gc
import gzip
import hashlib
import io
import json
import platform
import sys
import time
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import average_precision_score
from comportamiento import FEATURES,build_features
from ronda3_modeling import CONFIGS,NUMERIC,CATEGORICAL,build_model

BASE=Path(os.environ.get('FINAN_EXPERIMENT_DIR','data/experimentos')).resolve()
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'ronda1'))
from comparar_finan import normalize,threshold_curve,at_threshold

COSTS=[5,10,25,50,100]
CAPACITIES=[10,25,50,100,250]
WINDOWS=[(2015,'2014-01-01'),(2016,'2015-07-01'),(2019,'2018-07-01')]
SOURCE_COLUMNS=['source_card_id','source_client_id','source_merchant_id','source_merchant_city']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def write_bytes(path,payload):
    path=Path(path);temporary=path.with_name(path.name+'.partial')
    temporary.write_bytes(payload);temporary.replace(path)


def write_json(path,value):
    write_bytes(path,json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode())


def write_csv(path,frame):
    payload=frame.to_csv(index=False).encode()
    if str(path).endswith('.gz'):payload=gzip.compress(payload,compresslevel=6,mtime=0)
    write_bytes(path,payload)


def predict(model,frame):
    positive=int(np.flatnonzero(model.classes_==1)[0])
    return np.concatenate([model.predict_proba(frame.iloc[i:i+50000])[:,positive]
                           for i in range(0,len(frame),50000)])


def choose(curve,cost):
    values=curve.fp.to_numpy()+cost*curve.fn.to_numpy()
    i=int(np.argmin(values))
    return {**curve.iloc[i].to_dict(),'cost':int(values[i])}


def run():
    out=BASE/'finan_ronda3/experimento'
    out.mkdir(parents=True,exist_ok=False)
    source=BASE/'finan_datos_recibidos/finan_desarrollo.csv.gz'
    context=BASE/'contexto/desarrollo_contexto.csv.gz'
    previous=BASE/'finan_ronda2/experimento'
    info=json.loads(Path(str(source)+'.json').read_text())
    assert sha(source)==info['file_sha256']
    assert info['excluded_test_ids_sha256']=='3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08'
    assert info['test_excluded'] is True
    source_manifest=json.loads(Path(str(context)+'.json').read_text())
    context_hash=source_manifest['file_sha256']
    assert sha(context)==context_hash
    assert json.loads((previous/'estado.json').read_text())['status']=='completed_exploratory_round2'
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'retrospective_exploratory_round3_on_already_explored_development',
        'max_new_fits':6,'configs':CONFIGS,'new_features':FEATURES,'trees':200,
        'max_depth':16,'min_samples_leaf':2,'max_features':'sqrt','seed':42,
        'training_jobs':8,'prediction_jobs':1,'fraud_weight':1,
        'source_sha256':sha(source),'context_sha256':context_hash,
        'test_s9_excluded_by_exact_known_development_whitelist':True,
        'history':'Only preceding timestamp blocks in the same verified development sample; no labels.',
        'online_context_updates':'Previous validation/evaluation transactions may update unsupervised history before later events; no model refit or label updates.',
        'same_timestamp_events_excluded_from_each_others_history':True,
        'amount_history_uses_absolute_amount':True,
        'ratio_denominator_floor':1.0,
        'new_attributes_from_user_card_snapshots':False,
        'cost_fp':1,'cost_fn':COSTS,'costs_hypothetical':True,
        'capacity_validation_per_10000':CAPACITIES,
        'selection':'Minimum validation cost, then fewer validation alerts, then candidate name. Within candidate, fewer alerts then higher threshold.',
        'capacity_selection':'Maximum validation recall within capacity, then fewer validation false alerts, then candidate name.',
        'no_resampling_validation_or_evaluation':True,'no_refit_after_selection':True,
        'no_official_model_promotion':True,'independent_final_test':False,
        'windows':[{'evaluation_year':y,'validation_start':s,'validation_end_exclusive':f'{y}-01-01'} for y,s in WINDOWS],
        'software':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,
                    'sklearn':sklearn.__version__,'joblib':joblib.__version__},
        'code_hashes':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')}}
    write_json(out/'protocolo_ronda3.json',protocol)
    write_json(out/'estado.json',{'status':'feature_preparation','completed_fits':0})
    data=normalize(pd.read_csv(source))
    extra=pd.read_csv(context,usecols=['transaction_id']+SOURCE_COLUMNS,dtype={c:'string' for c in SOURCE_COLUMNS}).set_index('transaction_id')
    assert extra.index.is_unique and set(extra.index)==set(data.transaction_id)
    assert len(data)==841721 and int(data.is_fraud.sum())==1201
    for c in SOURCE_COLUMNS:data[c]=data.transaction_id.map(extra[c])
    print('Construyendo antecedentes estrictamente previos para 841.721 operaciones...',flush=True)
    generated=build_features(data)
    assert generated.index.equals(pd.Index(data.transaction_id,name='transaction_id'))
    write_csv(out/'variables_comportamiento.csv.gz',generated.reset_index())
    for c in FEATURES:data[c]=generated[c].to_numpy()
    del extra,generated
    feature_hash=sha(out/'variables_comportamiento.csv.gz')
    write_json(out/'integridad_variables.json',{'sha256':feature_hash,'rows':len(data),'features':FEATURES,
        'missing_per_feature':{c:int(data[c].isna().sum()) for c in FEATURES}})
    old_hashes={x['file']:x['sha256'] for x in json.loads((previous/'integridad_predicciones.json').read_text())}
    old_names=sorted(pd.read_csv(previous/'seleccion_validacion.csv').candidate.unique())
    assert len(old_names)==11
    rows=[];decisions=[];frontier=[];models=[];prediction_hashes=[]
    Xcols=NUMERIC+CATEGORICAL+FEATURES

    def score_candidate(year,name,stage,val,ev,pval,peval):
        curve=threshold_curve(val.is_fraud,pval)
        cost_choices={k:choose(curve,k) for k in COSTS}
        caps={cap:curve[curve.alerts_per_10000<=cap].sort_values(['tp','fp','threshold'],ascending=[False,True,False]).iloc[0].to_dict()
              for cap in CAPACITIES}
        f1_choice=curve.sort_values(['f1','alerts','threshold'],ascending=[False,True,False]).iloc[0].to_dict()
        write_csv(out/f'curva_{year}_{name}.csv.gz',curve)
        write_json(out/f'umbrales_{year}_{name}.json',{'cost':cost_choices,'capacity':caps,'f1_reference':f1_choice})
        if callable(peval):peval=peval()
        for split,frame,p in [('validation',val,pval),('evaluation',ev,peval)]:
            pred=pd.DataFrame({'transaction_id':frame.transaction_id.to_numpy(),'is_fraud':frame.is_fraud.to_numpy(),'score':p})
            path=out/f'predicciones_{year}_{name}_{split}.csv.gz'
            write_csv(path,pred)
            prediction_hashes.append({'file':path.name,'sha256':sha(path),'rows':len(frame)})
        ap=float(average_precision_score(ev.is_fraud,peval))
        for k,c in cost_choices.items():
            decisions.append({'evaluation_year':year,'candidate':name,'round':stage,'cost_fn':k,**c})
            measured=at_threshold(ev.is_fraud,peval,c['threshold'])
            rows.append({'evaluation_year':year,'candidate':name,'round':stage,'cost_fn':k,'threshold':c['threshold'],
                         **measured,'cost':measured['fp']+k*measured['fn'],'average_precision':ap})
        for cap,c in caps.items():
            measured=at_threshold(ev.is_fraud,peval,c['threshold'])
            frontier.append({'evaluation_year':year,'candidate':name,'round':stage,'capacity_validation_per_10000':cap,
                'threshold':c['threshold'],'validation_tp':c['tp'],'validation_fp':c['fp'],
                'validation_recall':c['recall'],'validation_alerts_per_10000':c['alerts_per_10000'],**measured})
        write_csv(out/'comparacion_ronda3.csv',pd.DataFrame(rows))
        write_csv(out/'seleccion_validacion.csv',pd.DataFrame(decisions))
        write_csv(out/'frontera_capacidad.csv',pd.DataFrame(frontier))
        return peval

    for year,start in WINDOWS:
        val=data[(data.transaction_date>=start)&(data.transaction_date<f'{year}-01-01')]
        ev=data[data.transaction_date.dt.year==year]
        train=data[data.transaction_date<start]
        assert train.transaction_date.max()<val.transaction_date.min()<ev.transaction_date.min()
        assert train.transaction_id.is_unique and val.is_fraud.sum()>=30
        assignment=pd.concat([pd.DataFrame({'transaction_id':g.transaction_id,'partition':split}) for split,g in [('train',train),('validation',val),('evaluation',ev)]])
        assert assignment.transaction_id.is_unique
        write_csv(out/f'particiones_{year}.csv.gz',assignment)
        for name in old_names:
            frames=[]
            for split,g in [('validation',val),('evaluation',ev)]:
                p=previous/f'predicciones_{year}_{name}_{split}.csv.gz'
                assert sha(p)==old_hashes[p.name]
                old=pd.read_csv(p,float_precision='round_trip').set_index('transaction_id')
                assert set(old.index)==set(g.transaction_id)
                aligned=old.loc[g.transaction_id]
                assert np.array_equal(aligned.is_fraud.to_numpy(),g.is_fraud.to_numpy())
                frames.append(aligned.score.to_numpy())
            score_candidate(year,name,'previous',val,ev,*frames)
        for config in CONFIGS:
            name=config['name']
            print(f'{year}: entrenando {name}; {len(train)} operaciones, {int(train.is_fraud.sum())} fraudes.',flush=True)
            write_json(out/'estado.json',{'status':'training','completed_fits':len(models),'active_year':year,'active_candidate':name})
            model=build_model(config,jobs=8)
            started=time.perf_counter();model.fit(train[Xcols],train.is_fraud)
            elapsed=time.perf_counter()-started
            model.set_params(model__n_jobs=1)
            buffer=io.BytesIO();joblib.dump(model,buffer,compress=3)
            model_path=out/f'modelo_{year}_{name}.joblib';write_bytes(model_path,buffer.getvalue());del buffer
            pval=predict(model,val[Xcols])
            peval=score_candidate(year,name,'new_context',val,ev,pval,lambda:predict(model,ev[Xcols]))
            restored=joblib.load(model_path)
            assert np.array_equal(predict(restored,ev[Xcols].iloc[:256]),peval[:256])
            models.append({'evaluation_year':year,'candidate':name,'reference':config['reference'],
                'train_start':str(train.transaction_date.min()),'train_end':str(train.transaction_date.max()),
                'train_rows':len(train),'train_frauds':int(train.is_fraud.sum()),
                'validation_rows':len(val),'validation_frauds':int(val.is_fraud.sum()),
                'evaluation_rows':len(ev),'evaluation_frauds':int(ev.is_fraud.sum()),
                'fit_seconds':elapsed,'model_sha256':sha(model_path),'persistence_256_predictions_exact':True})
            write_csv(out/'modelos_y_tiempos.csv',pd.DataFrame(models))
            print(f'Completado {name} ({year}); entrenamiento {elapsed:.1f} s.',flush=True)
            del model,restored,pval,peval
            gc.collect()
    selection=pd.DataFrame(decisions);metrics=pd.DataFrame(rows);capacity=pd.DataFrame(frontier)
    winners=[];cap_winners=[]
    for pool in ['previous','new_context','all']:
        eligible=selection if pool=='all' else selection[selection['round']==pool]
        best=eligible.sort_values(['cost','alerts','candidate']).groupby(['evaluation_year','cost_fn']).head(1).copy()
        best['pool']=pool
        winners.append(best.merge(metrics,on=['evaluation_year','candidate','cost_fn'],suffixes=('_validation','_evaluation')))
        eligible_cap=capacity if pool=='all' else capacity[capacity['round']==pool]
        best_cap=eligible_cap.sort_values(['validation_tp','validation_fp','candidate'],ascending=[False,True,True]).groupby(['evaluation_year','capacity_validation_per_10000']).head(1).copy()
        best_cap['pool']=pool;cap_winners.append(best_cap)
    write_csv(out/'ganadores_validacion_y_evaluacion.csv',pd.concat(winners,ignore_index=True))
    write_csv(out/'ganadores_capacidad.csv',pd.concat(cap_winners,ignore_index=True))
    write_json(out/'integridad_predicciones.json',prediction_hashes)
    write_json(out/'estado.json',{'status':'completed_exploratory_round3','completed_fits':len(models),
        'candidates_per_window':13,'metric_rows':len(rows),'independent_final_test':False,'official_model_replaced':False})
    print('Terminados seis entrenamientos y comparación con 11 referencias por ventana.',flush=True)


if __name__=='__main__':run()
