"""Estudio retrospectivo adicional: siete configuraciones en tres ventanas.

Las etiquetas de evaluación ya se exploraron en R1; no se presenta como test nuevo.
Se fijan candidatos y ventanas antes de entrenar. Selección por costo de validación.
"""
import argparse
import gc
import gzip
import hashlib
import io
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import average_precision_score, roc_auc_score

from ronda2_modeling import CONFIGS, NUMERIC, CATEGORICAL, REVISED_EXCLUSIONS, build_model

COSTS = [5,10,25,50,100]
CAPACITIES = [10,25,50,100,250]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    payload=json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False).encode()
    atomic_bytes(path,payload)


def atomic_bytes(path, payload):
    path=Path(path); temporary=path.with_name(path.name+".partial")
    temporary.write_bytes(payload);temporary.replace(path)


def write_csv(path, df):
    payload=df.to_csv(index=False).encode("utf-8")
    if str(path).endswith(".gz"):
        payload=gzip.compress(payload,compresslevel=6,mtime=0)
        gzip.decompress(payload)
    atomic_bytes(path,payload)


def choose(curve, cost_fn, capacity=None):
    c=curve if capacity is None else curve[curve.alerts_per_10000<=capacity]
    cost=c.fp.to_numpy()+cost_fn*c.fn.to_numpy()
    # La curva viene ordenada por menor número de alertas y mayor umbral.
    i=int(np.argmin(cost))
    result=c.iloc[i].to_dict();result["cost"]=int(cost[i])
    return result


def predict(model, X):
    positive=int(np.flatnonzero(model.classes_==1)[0])
    return np.concatenate([model.predict_proba(X.iloc[i:i+50000])[:,positive] for i in range(0,len(X),50000)])


def define_windows(data):
    windows=[]
    for year in [2015,2016,2019]:
        proposed=pd.Timestamp(year=year-1,month=7,day=1)
        end=pd.Timestamp(year=year,month=1,day=1)
        val=data[(data.transaction_date>=proposed)&(data.transaction_date<end)]
        fallback=int(val.is_fraud.sum())<30
        start=pd.Timestamp(year=year-1,month=1,day=1) if fallback else proposed
        validation=np.flatnonzero(((data.transaction_date>=start)&(data.transaction_date<end)).to_numpy())
        evaluation=np.flatnonzero((data.transaction_date.dt.year==year).to_numpy())
        assert data.iloc[validation].is_fraud.sum()>=30
        windows.append({"year":year,"start":start,"end":end,"validation":validation,
                        "evaluation":evaluation,"extended_validation_for_support":fallback})
    return windows


def run(data_path, previous, output, jobs=8):
    if output.exists():raise ValueError("La carpeta de resultados debe ser nueva.")
    output.mkdir(parents=True)
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"ronda1"))
    from comparar_finan import normalize, threshold_curve, at_threshold
    info=json.loads(Path(str(data_path)+".json").read_text())
    if sha(data_path)!=info["file_sha256"] or info.get("test_excluded") is not True:
        raise ValueError("Datos/manifiesto distintos o exclusión de test no declarada.")
    if info.get("excluded_test_ids_sha256") != "3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08":
        raise ValueError("No coincide la partición S9 excluida.")
    data=normalize(pd.read_csv(data_path))
    if len(data)!=841721 or int(data.is_fraud.sum())!=1201:raise ValueError("Conteos distintos a R1.")
    windows=define_windows(data)
    protocol={"created_utc":datetime.now(timezone.utc).isoformat(),
              "scope":"exploratory_second_round_on_previously_observed_historical_development",
              "rationale":"Auditoría identifica categorías nuevas en 2015 y cambio de fraude online a chip antes de 2019.",
              "input_sha256":sha(data_path),"original_test_excluded_as_declared_in_manifest":True,
              "evaluation_years":[2015,2016,2019],"validation_rule":"Últimos seis meses del año previo; extender a doce si hay menos de 30 fraudes.",
              "configs":CONFIGS,"max_new_fits":21,"trees":200,"seed":42,
              "training_jobs":jobs,"prediction_jobs":1,
              "recent_window":"36 meses inmediatamente anteriores al inicio de validación",
              "revised_features":{"excluded":REVISED_EXCLUSIONS,"use_chip_mapping":{"Chip Transaction":"Presencial","Swipe Transaction":"Presencial","Online Transaction":"En linea"}},
              "cost_fp":1,"cost_fn_scenarios":COSTS,"costs_are_hypothetical":True,
              "hypothetical_alerts_per_10000":CAPACITIES,
              "selection":"Costo mínimo en validación común a los 11 candidatos; desempate menos alertas y nombre. Umbral: menos alertas, mayor umbral.",
              "unchanged_evaluation_ids":True,"no_resampling_validation_or_evaluation":True,
              "no_refit_after_selection":True,"no_model_promotion":True,
              "software":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__,"joblib":joblib.__version__},
              "source_code_sha256":{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
              "windows":[]}
    for w in windows:
        protocol["windows"].append({"evaluation_year":w["year"],"validation_start":str(w["start"]),
                                    "validation_end_exclusive":str(w["end"]),
                                    "validation_rows":len(w["validation"]),"validation_frauds":int(data.iloc[w["validation"]].is_fraud.sum()),
                                    "evaluation_rows":len(w["evaluation"]),"evaluation_frauds":int(data.iloc[w["evaluation"]].is_fraud.sum()),
                                    "extended_validation_for_support":w["extended_validation_for_support"]})
    write_json(output/"protocolo_ronda2.json",protocol)
    write_json(output/"estado.json",{"status":"running","completed_fits":0})
    rows=[];choices=[];budgetrows=[];modelrows=[];integrity=[]

    def score_candidate(year,name,stage,validation,evaluation,pval,peval):
        curve=threshold_curve(validation.is_fraud,pval)
        write_csv(output/f"curva_{year}_{name}.csv.gz",curve)
        maximum=curve.sort_values(["f1","alerts","threshold"],ascending=[False,True,False]).iloc[0]
        decisions={cost:choose(curve,cost) for cost in COSTS}
        capacity_decisions={(cost,cap):choose(curve,cost,cap) for cost in COSTS for cap in CAPACITIES}
        write_json(output/f"umbrales_{year}_{name}.json",{"selection_start":str(validation.transaction_date.min()),
                  "selection_end":str(validation.transaction_date.max()),"cost":decisions,"f1":float(maximum.threshold)})
        # Las decisiones se fijaron antes de obtener puntuaciones posteriores en modelos nuevos.
        if callable(peval):peval=peval()
        for split,group,score in [("validation",validation,pval),("evaluation",evaluation,peval)]:
            predictionframe=pd.DataFrame({"transaction_id":group.transaction_id.to_numpy(),"is_fraud":group.is_fraud.to_numpy(),"score":score})
            path=output/f"predicciones_{year}_{name}_{split}.csv.gz"
            write_csv(path,predictionframe)
            integrity.append({"file":path.name,"sha256":sha(path),"rows":len(group),"frauds":int(group.is_fraud.sum())})
        ap=float(average_precision_score(evaluation.is_fraud,peval));auc=float(roc_auc_score(evaluation.is_fraud,peval))
        for cost in COSTS:
            choices.append({"evaluation_year":year,"candidate":name,"round":stage,"cost_fn":cost,**decisions[cost]})
            for policy,t in [("costo",decisions[cost]["threshold"]),("f1_validacion",float(maximum.threshold)),("referencia_007217143",.07217143)]:
                metrics=at_threshold(evaluation.is_fraud,peval,t)
                rows.append({"evaluation_year":year,"candidate":name,"round":stage,"policy":policy,"cost_fn":cost,"threshold":t,
                             **metrics,"cost":metrics["fp"]+cost*metrics["fn"],"average_precision":ap,"roc_auc":auc})
            for cap in CAPACITIES:
                c=capacity_decisions[cost,cap];measured=at_threshold(evaluation.is_fraud,peval,c["threshold"])
                budgetrows.append({"evaluation_year":year,"candidate":name,"round":stage,"cost_fn":cost,"capacity_per_10000":cap,
                                   "threshold":c["threshold"],"validation_tp":c["tp"],"validation_fp":c["fp"],"validation_fn":c["fn"],
                                   "validation_cost":c["cost"],"validation_alerts_per_10000":c["alerts_per_10000"],
                                   **measured,"cost":measured["fp"]+cost*measured["fn"]})
        write_csv(output/"comparacion_ronda2.csv",pd.DataFrame(rows))
        write_csv(output/"seleccion_validacion.csv",pd.DataFrame(choices))
        write_csv(output/"capacidad_validacion_y_evaluacion.csv",pd.DataFrame(budgetrows))

    for w in windows:
        year=w["year"];validation=data.iloc[w["validation"]];evaluation=data.iloc[w["evaluation"]]
        ref_assignment=pd.read_csv(previous/f"resultados/particiones_{year}.csv.gz")
        assert set(ref_assignment.query("partition=='evaluation'").transaction_id)==set(evaluation.transaction_id)
        for strategy in ["sin_balanceo","submuestreo","smotenc","pesos_clase"]:
            name="r1_"+strategy
            pv=pd.read_csv(previous/f"resultados/predicciones_{year}_{strategy}_validation.csv.gz",float_precision="round_trip").set_index("transaction_id")
            pe=pd.read_csv(previous/f"resultados/predicciones_{year}_{strategy}_evaluation.csv.gz",float_precision="round_trip").set_index("transaction_id")
            assert np.array_equal(pv.loc[validation.transaction_id].is_fraud,validation.is_fraud)
            assert np.array_equal(pe.loc[evaluation.transaction_id].is_fraud,evaluation.is_fraud)
            score_candidate(year,name,"R1_rethresholded_common_validation",validation,evaluation,
                            pv.loc[validation.transaction_id].score.to_numpy(),pe.loc[evaluation.transaction_id].score.to_numpy())
        for cfg in CONFIGS:
            name=cfg["name"]
            lower=data.transaction_date.min() if cfg["recent_years"] is None else w["start"]-pd.DateOffset(years=cfg["recent_years"])
            train=data[(data.transaction_date>=lower)&(data.transaction_date<w["start"])]
            assert train.transaction_date.max()<validation.transaction_date.min()<evaluation.transaction_date.min()
            assert not set(train.transaction_id).intersection(validation.transaction_id)
            print(f"{year}: entrenando {name}; {len(train)} filas, {int(train.is_fraud.sum())} fraudes",flush=True)
            model=build_model(cfg,jobs=jobs);began=time.perf_counter()
            model.fit(train[NUMERIC+CATEGORICAL],train.is_fraud)
            seconds=time.perf_counter()-began
            model.set_params(model__n_jobs=1)
            buf=io.BytesIO();joblib.dump(model,buf,compress=3)
            path=output/f"modelo_{year}_{name}.joblib";atomic_bytes(path,buf.getvalue());del buf
            modelrows.append({"evaluation_year":year,"candidate":name,"train_start":str(train.transaction_date.min()),
                              "train_end":str(train.transaction_date.max()),"train_rows":len(train),"train_frauds":int(train.is_fraud.sum()),
                              "fit_seconds":seconds,"model_sha256":sha(path)})
            assignment=pd.concat([pd.DataFrame({"transaction_id":g.transaction_id.to_numpy(),"partition":split})
                                  for split,g in [("train",train),("validation",validation),("evaluation",evaluation)]])
            write_csv(output/f"particiones_{year}_{name}.csv.gz",assignment)
            pval=predict(model,validation[NUMERIC+CATEGORICAL])
            score_candidate(year,name,"R2_new_fit",validation,evaluation,pval,lambda:predict(model,evaluation[NUMERIC+CATEGORICAL]))
            write_csv(output/"modelos_y_tiempos.csv",pd.DataFrame(modelrows))
            write_json(output/"estado.json",{"status":"running","completed_fits":len(modelrows)})
            del model,train,assignment,pval
            gc.collect()
    choiceframe=pd.DataFrame(choices);resultframe=pd.DataFrame(rows)
    allwinners=[]
    for pool in ["R1","R2","todas"]:
        poolframe=choiceframe if pool=="todas" else choiceframe[choiceframe["round"].str.startswith(pool)]
        winners=poolframe.sort_values(["cost","alerts","candidate"]).groupby(["evaluation_year","cost_fn"]).head(1).copy()
        winners["pool"]=pool
        merged=winners.merge(resultframe[resultframe.policy=="costo"],on=["evaluation_year","candidate","cost_fn"],suffixes=("_validation","_evaluation"))
        allwinners.append(merged)
    write_csv(output/"ganadores_validacion_y_evaluacion.csv",pd.concat(allwinners,ignore_index=True).sort_values(["evaluation_year","cost_fn","pool"]))
    write_json(output/"integridad_predicciones.json",integrity)
    write_json(output/"estado.json",{"status":"completed_exploratory_round2","completed_fits":len(modelrows),
                                      "candidates_per_window":11,"evaluation_metric_rows":len(rows),
                                      "independent_final_test":False,"official_model_replaced":False})
    print(f"Terminados {len(modelrows)} entrenamientos; {len(rows)} filas de evaluación.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--previous",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--jobs",type=int,default=8)
    args=parser.parse_args()
    run(args.data.resolve(),args.previous.resolve(),args.output.resolve(),args.jobs)
