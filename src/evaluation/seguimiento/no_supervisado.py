"""Contraste temporal con Isolation Forest; no utiliza etiquetas para ajustar el detector.

Los parámetros se fijan antes de ajustar tres ventanas. Las etiquetas de validación
se usan solo para escoger el umbral operativo. Es un estudio retrospectivo de
desarrollo, separado de la decisión R1-R3 y del test S9.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import platform
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ronda1"))
sys.path.insert(0, str(HERE / "ronda2"))
from comparar_finan import normalize, threshold_curve
from ronda2_modeling import NUMERIC, CATEGORICAL, CONFIGS, build_model

WINDOWS = [(2015, "2014-01-01"), (2016, "2015-07-01"), (2019, "2018-07-01")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_bytes(path, payload):
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_json(path, data):
    write_bytes(path, (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def write_csv(path, frame):
    payload = frame.to_csv(index=False).encode("utf-8")
    if str(path).endswith(".gz"):
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
        gzip.decompress(payload)
    write_bytes(path, payload)


def metrics(y, score, threshold, review_cost, fn_cost):
    tn, fp, fn, tp = confusion_matrix(y, score >= threshold, labels=[0, 1]).ravel()
    return {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
            "recall": float(tp / (tp + fn)), "precision": float(tp / (tp + fp)) if tp + fp else 0.,
            "f1": float(2 * tp / (2 * tp + fp + fn)),
            "average_precision": float(average_precision_score(y, score)),
            "roc_auc": float(roc_auc_score(y, score)),
            "alerts_per_10000": float((tp + fp) / len(y) * 10000),
            "cost": float(review_cost * (tp + fp) + fn_cost * fn)}


def run(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Seleccione una carpeta --output nueva; se conservan las ejecuciones anteriores.")
    info = json.loads(Path(str(args.data) + ".json").read_text())
    if sha(args.data) != info["file_sha256"] or info.get("test_excluded") is not True:
        raise ValueError("La exportación debe excluir el test S9 y coincidir con su manifiesto.")
    if info["excluded_test_ids_sha256"] != "3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08":
        raise ValueError("No coincide la partición S9 excluida.")
    data = normalize(pd.read_csv(args.data))
    if len(data) != 841721 or data.is_fraud.sum() != 1201 or not data.transaction_id.is_unique:
        raise ValueError("Desarrollo diferente al documentado.")
    output.mkdir(parents=True)
    params = dict(n_estimators=200, max_samples=4096, contamination="auto",
                  max_features=1.0, bootstrap=False, random_state=42, n_jobs=args.jobs)
    write_json(output / "protocolo.json", {
        "scope": "retrospective_development_comparison", "data_sha256": sha(args.data),
        "s9_test_excluded": True, "max_new_fits": 3, "estimator": "IsolationForest",
        "parameters": params, "fit_uses_labels": False, "score": "negative score_samples; not a probability",
        "preprocessing": "same numeric/ordinal/one-hot pipeline as rf_actualizado; fitted on training only",
        "windows": WINDOWS, "selection": "validation cost minimum; ties fewer alerts and higher threshold",
        "review_cost": 3, "fn_cost": "0.5 * mean(max(amount,0)) of training frauds",
        "capacity_per_10000": 50, "rf_reference": "archived R2 rf_actualizado predictions",
        "no_model_promotion": True, "independent_final_test": False,
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "pandas": pd.__version__, "sklearn": sklearn.__version__, "joblib": joblib.__version__},
    })
    records, timings = [], []
    for year, start in WINDOWS:
        train = data[data.transaction_date < start]
        val = data[(data.transaction_date >= start) & (data.transaction_date < f"{year}-01-01")]
        ev = data[data.transaction_date.dt.year == year]
        loss = float(train.loc[train.is_fraud == 1, "amount"].clip(lower=0).mean()) * .5
        print(f"Isolation Forest {year}: {len(train)} entrenamiento, {len(val)} validación, {len(ev)} evaluación", flush=True)
        model = build_model(CONFIGS[0], jobs=args.jobs)
        model.set_params(model=IsolationForest(**params))
        began = time.perf_counter()
        model.fit(train[NUMERIC + CATEGORICAL])
        fit_seconds = time.perf_counter() - began
        path = output / f"isolation_forest_{year}.joblib"
        joblib.dump(model, path, compress=3)
        timings.append({"evaluation_year": year, "train_rows": len(train), "train_frauds": int(train.is_fraud.sum()),
                        "validation_rows": len(val), "validation_frauds": int(val.is_fraud.sum()),
                        "evaluation_rows": len(ev), "evaluation_frauds": int(ev.is_fraud.sum()),
                        "fit_seconds": fit_seconds, "model_sha256": sha(path), "model_bytes": path.stat().st_size})
        def score_frame(frame):
            return np.concatenate([-model.score_samples(frame.iloc[i:i+50000][NUMERIC+CATEGORICAL])
                                   for i in range(0, len(frame), 50000)])
        score_start = time.perf_counter()
        pval = score_frame(val)
        # All choices for both candidates are fixed before reading evaluation scores.
        rfval = pd.read_csv(args.rf_predictions / f"predicciones_{year}_rf_actualizado_validation.csv.gz",
                            float_precision="round_trip").set_index("transaction_id").loc[val.transaction_id]
        assert np.array_equal(rfval.is_fraud, val.is_fraud)
        selected = []
        for name, scores in [("isolation_forest", pval), ("rf_actualizado", rfval.score.to_numpy())]:
            curve = threshold_curve(val.is_fraud, scores)
            curve["business_cost"] = 3 * (curve.tp + curve.fp) + loss * curve.fn
            cost_choice = curve[curve.alerts_per_10000 <= 50].sort_values(
                ["business_cost", "alerts", "threshold"], ascending=[True, True, False]).iloc[0]
            f1_choice = curve.sort_values(["f1", "alerts", "threshold"], ascending=[False, True, False]).iloc[0]
            write_csv(output / f"curva_{year}_{name}.csv.gz", curve)
            for policy, chosen in [("costo_capacidad_50", cost_choice), ("f1_validacion", f1_choice)]:
                selected.append({"candidate": name, "policy": policy, "threshold": float(chosen.threshold),
                                 "fn_cost": loss, "validation_cost": float(chosen.business_cost),
                                 "validation_tp": int(chosen.tp), "validation_fp": int(chosen.fp),
                                 "validation_recall": float(chosen.recall)})
        write_json(output / f"decisiones_{year}.json", selected)
        peval = score_frame(ev)
        timings[-1]["score_seconds_validation_and_evaluation"] = time.perf_counter() - score_start
        rfeval = pd.read_csv(args.rf_predictions / f"predicciones_{year}_rf_actualizado_evaluation.csv.gz",
                             float_precision="round_trip").set_index("transaction_id").loc[ev.transaction_id]
        assert np.array_equal(rfeval.is_fraud, ev.is_fraud)
        for split, frame, score in [("validation", val, pval), ("evaluation", ev, peval)]:
            write_csv(output / f"predicciones_{year}_isolation_forest_{split}.csv.gz",
                      pd.DataFrame({"transaction_id": frame.transaction_id.to_numpy(),
                                    "is_fraud": frame.is_fraud.to_numpy(), "score": score}))
        for choice in selected:
            scores = peval if choice["candidate"] == "isolation_forest" else rfeval.score.to_numpy()
            records.append({"evaluation_year": year, **choice,
                            **metrics(ev.is_fraud, scores, choice["threshold"], 3, loss)})
        write_csv(output / "comparacion.csv", pd.DataFrame(records))
        write_csv(output / "modelos_y_tiempos.csv", pd.DataFrame(timings))
    write_json(output / "estado.json", {"status": "completed", "new_fits": 3,
                                        "s9_test_excluded": True, "official_model_replaced": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--rf-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    run(parser.parse_args())
