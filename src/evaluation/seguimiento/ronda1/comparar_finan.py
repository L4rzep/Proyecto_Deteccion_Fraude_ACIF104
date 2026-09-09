"""Estudio histórico de RF, balanceo y costos. No sobrescribe el modelo oficial.

profile inspecciona los datos. run exige una exportación de desarrollo verificada.
Los resultados son retrospectivos; no constituyen un nuevo test independiente.
"""
from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from extraer_desarrollo import CATEGORICAL, COLUMNS, NUMERIC, sha256

STRATEGIES = ["sin_balanceo", "submuestreo", "smotenc", "pesos_clase"]
COST_RATIOS = [5, 10, 25, 50, 100]


def load_balancing_snapshot():
    """Use the licensed source revision from the recorded R1 experiment."""
    root = Path(__file__).resolve().parents[4] / "third_party" / "ronda1"
    manifest = json.loads((root / "manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        if sha256(root / relative) != expected:
            raise ValueError(f"La dependencia R1 cambió: {relative}")
    sys.path.insert(0, str(root))


def write_csv(path, frame):
    """Finish and validate compression before publishing each output file."""
    path = Path(path)
    payload = frame.to_csv(index=False).encode("utf-8")
    if path.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
        gzip.decompress(payload)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_json(path, content):
    Path(path).write_text(json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def normalize(data):
    missing = set(COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f"Faltan columnas: {sorted(missing)}")
    data = data[COLUMNS].copy()
    if not len(data):
        raise ValueError("El archivo está vacío.")
    ids = pd.to_numeric(data.transaction_id, errors="raise")
    if ids.isna().any() or ids.duplicated().any() or ((ids % 1) != 0).any():
        raise ValueError("Los identificadores deben ser enteros únicos no nulos.")
    data["transaction_id"] = ids.astype("int64")
    labels = data.is_fraud.astype(str).str.strip().str.lower()
    mapped = labels.map({"0": 0, "1": 1, "0.0": 0, "1.0": 1,
                         "false": 0, "true": 1, "no": 0, "yes": 1})
    if mapped.isna().any():
        raise ValueError("Hay etiquetas de fraude ausentes o desconocidas.")
    data["is_fraud"] = mapped.astype("int8")
    data["transaction_date"] = pd.to_datetime(data.transaction_date, errors="raise")
    if data.transaction_date.isna().any():
        raise ValueError("Hay fechas ausentes.")
    for name in NUMERIC:
        converted = pd.to_numeric(data[name], errors="coerce")
        if (data[name].notna() & converted.isna()).any() or np.isinf(converted).any():
            raise ValueError(f"Valores numéricos inválidos en {name}; no se sustituyen por cero.")
        data[name] = converted.astype("float64")
    for name in CATEGORICAL:
        # Se conservan etiquetas como Chip Transaction, Mastercard y YES.
        data[name] = data[name].map(lambda v: np.nan if pd.isna(v) else str(v)).astype(object)
    return data.sort_values(["transaction_date", "transaction_id"]).reset_index(drop=True)


def profile(data):
    rows = []
    for year, group in data.groupby(data.transaction_date.dt.year, sort=True):
        positives = int(group.is_fraud.sum())
        rows.append({"year": int(year), "rows": len(group), "frauds": positives,
                     "non_frauds": len(group) - positives,
                     "prevalence": positives / len(group),
                     "first_date": str(group.transaction_date.min()),
                     "last_date": str(group.transaction_date.max())})
    return pd.DataFrame(rows)


def temporal_folds(data, last_folds=3, min_positives=30):
    years = data.transaction_date.dt.year.to_numpy()
    target = data.is_fraud.to_numpy()
    result, excluded = [], []
    for year in sorted(set(years)):
        train = np.flatnonzero(years < year - 1)
        validation = np.flatnonzero(years == year - 1)
        evaluation = np.flatnonzero(years == year)
        counts = {name: {"rows": len(idx), "frauds": int(target[idx].sum()),
                         "non_frauds": int(len(idx) - target[idx].sum())}
                  for name, idx in [("train", train), ("validation", validation), ("evaluation", evaluation)]}
        if any(c["frauds"] < min_positives or c["non_frauds"] == 0 for c in counts.values()):
            excluded.append({"evaluation_year": int(year), "reason": "Soporte de clases insuficiente", "counts": counts})
            continue
        result.append({"year": int(year), "train": train, "validation": validation,
                       "evaluation": evaluation, "counts": counts})
    return result[-last_folds:], excluded


def metrics_counts(tp, fp, fn, tn):
    tp, fp, fn, tn = map(int, (tp, fp, fn, tn))
    rows = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "rows": rows,
            "precision": precision, "recall": recall, "f1": f1,
            "alerts": tp + fp, "alerts_per_10000": 10000 * (tp + fp) / rows,
            "fp_per_10000": 10000 * fp / rows}


def threshold_curve(y, p):
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    if not len(y) or len(y) != len(p) or not np.isin(y, [0, 1]).all():
        raise ValueError("Etiquetas/probabilidades inválidas o de distinta longitud.")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Las probabilidades deben estar entre 0 y 1.")
    order = np.argsort(-p, kind="stable")
    scores = p[order]
    ends = np.r_[np.flatnonzero(scores[:-1] != scores[1:]), len(scores) - 1]
    tp = np.r_[0, np.cumsum(y[order], dtype=np.int64)[ends]]
    alerts = np.r_[0, ends + 1]
    fp = alerts - tp
    fn = int(y.sum()) - tp
    tn = len(y) - int(y.sum()) - fp
    # Umbral >1 representa explícitamente no emitir ninguna alerta.
    thresholds = np.r_[np.nextafter(1.0, 2.0), scores[ends]]
    denominator = 2 * tp + fp + fn
    curve = pd.DataFrame({"threshold": thresholds, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                          "alerts": alerts, "rows": len(y)})
    curve["precision"] = np.divide(tp, alerts, out=np.zeros_like(tp, dtype=float), where=alerts > 0)
    curve["recall"] = tp / y.sum() if y.sum() else np.nan
    curve["f1"] = np.divide(2 * tp, denominator, out=np.zeros_like(tp, dtype=float), where=denominator > 0)
    curve["alerts_per_10000"] = alerts / len(y) * 10000
    return curve


def select_threshold(curve, cost_fn, budget=None):
    candidate = curve.copy()
    candidate["cost"] = candidate.fp + cost_fn * candidate.fn
    if budget is not None:
        candidate = candidate[candidate.alerts_per_10000 <= budget]
    # Regla fijada antes de evaluar: menor costo, menos alertas, mayor umbral.
    return candidate.sort_values(["cost", "alerts", "threshold"], ascending=[True, True, False]).iloc[0].to_dict()


def at_threshold(y, p, threshold):
    y, prediction = np.asarray(y), np.asarray(p) >= threshold
    return metrics_counts(((y == 1) & prediction).sum(), ((y == 0) & prediction).sum(),
                          ((y == 1) & ~prediction).sum(), ((y == 0) & ~prediction).sum())


def build_pipeline(strategy, ratio=0.1, trees=200, jobs=-1):
    load_balancing_snapshot()
    from imblearn.over_sampling import SMOTENC
    from imblearn.pipeline import Pipeline
    from imblearn.under_sampling import RandomUnderSampler
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    numeric = SkPipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                          ("scaler", StandardScaler())])
    categorical = SkPipeline([("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                              ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1))])
    preprocess = ColumnTransformer([("numeric", numeric, NUMERIC), ("categorical", categorical, CATEGORICAL)])
    cat_indices = list(range(len(NUMERIC), len(NUMERIC) + len(CATEGORICAL)))
    one_hot = ColumnTransformer([
        ("numeric", "passthrough", list(range(len(NUMERIC)))),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), cat_indices),
    ], sparse_threshold=1.0)
    sampler = "passthrough"
    if strategy == "submuestreo":
        sampler = RandomUnderSampler(sampling_strategy=ratio, random_state=42)
    elif strategy == "smotenc":
        sampler = SMOTENC(categorical_features=cat_indices, sampling_strategy=ratio,
                         k_neighbors=5, random_state=42)
    elif strategy not in ("sin_balanceo", "pesos_clase"):
        raise ValueError(f"Estrategia desconocida: {strategy}")
    forest = RandomForestClassifier(n_estimators=trees, max_depth=16, min_samples_leaf=2,
                                    max_features="sqrt", bootstrap=True, random_state=42, n_jobs=jobs,
                                    class_weight="balanced" if strategy == "pesos_clase" else None)
    return Pipeline([("preprocess", preprocess), ("sampler", sampler), ("onehot", one_hot), ("model", forest)])


def predict_chunks(model, data, chunks=50000):
    positive_index = int(np.flatnonzero(model.classes_ == 1)[0])
    return np.concatenate([model.predict_proba(data.iloc[start:start + chunks])[:, positive_index]
                           for start in range(0, len(data), chunks)])


def render_plots(out, curves, results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    latest = max(year for year, _ in curves)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for strategy in STRATEGIES:
        c = curves[(latest, strategy)]
        axes[0].plot(c.threshold.clip(upper=1), (c.fp + 10 * c.fn) / c.rows * 10000, label=strategy)
        axes[1].plot(c.alerts_per_10000, c.recall, label=strategy)
    axes[0].set(xlabel="Umbral", ylabel="Costo por 10.000 transacciones",
                title=f"Validación {latest - 1}: supuesto FP=1, FN=10")
    axes[1].set(xlabel="Alertas por 10.000 transacciones", ylabel="Recall",
                title=f"Validación {latest - 1}: cobertura y carga de revisión")
    for ax in axes:
        ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(out / "costos_y_alertas_validacion.png", dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    rows = results[(results.cost_fn == 10) & (results.policy == "costo")]
    for strategy, group in rows.groupby("strategy"):
        group = group.sort_values("evaluation_year")
        ax.plot(group.evaluation_year, group.recall, marker="o", label=strategy)
    ax.set(xlabel="Año posterior evaluado", ylabel="Recall", ylim=(0, 1),
           title="Comprobación temporal; umbral elegido el año anterior")
    ax.legend(fontsize=8); ax.grid(alpha=.2); fig.tight_layout()
    fig.savefig(out / "evolucion_temporal.png", dpi=160); plt.close(fig)


def run_study(data, out, config, source_info):
    load_balancing_snapshot()
    import imblearn
    import joblib
    import sklearn
    from sklearn.metrics import average_precision_score, roc_auc_score

    out.mkdir(parents=True, exist_ok=False)
    profile(data).to_csv(out / "perfil_por_ano.csv", index=False)
    folds, excluded = temporal_folds(data, config["last_folds"], config["min_positives"])
    protocol = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "historical_development_backtest_not_independent_final_test",
                "source": source_info, "configuration": config,
                "strategies": STRATEGIES, "cost_fp": 1, "cost_fn_scenarios": COST_RATIOS,
                "costs_are_hypothetical": True, "train_resampling_only": True,
                "no_refit_after_threshold_selection": True,
                "support_floor_note": "30 fraudes por segmento es un control operativo propuesto, no una exigencia del profesor ni garantía de precisión estadística.",
                "selection": "Validación únicamente; costo mínimo, menos alertas y mayor umbral en empates. Evaluación posterior descriptiva.",
                "folds": [{"evaluation_year": f["year"], "validation_year": f["year"] - 1,
                           "train_years_before": f["year"] - 1, "counts": f["counts"]} for f in folds],
                "excluded_years": excluded,
                "software": {"python": platform.python_version(), "numpy": np.__version__,
                             "pandas": pd.__version__, "sklearn": sklearn.__version__,
                             "imbalanced_learn": imblearn.__version__}}
    write_json(out / "protocolo.json", protocol)
    if len(folds) < 2:
        write_json(out / "estado.json", {"status": "blocked_insufficient_temporal_data", "folds": len(folds)})
        raise ValueError("Se requieren al menos dos ventanas temporales viables; consulte perfil_por_ano.csv y protocolo.json.")
    write_json(out / "estado.json", {"status": "running"})
    results, candidate_rows, budget_rows, fitted_rows, curves = [], [], [], [], {}
    try:
        for fold in folds:
            year = fold["year"]
            train = data.iloc[fold["train"]]
            validation = data.iloc[fold["validation"]]
            evaluation = data.iloc[fold["evaluation"]]
            if not (train.transaction_date.max() < validation.transaction_date.min()
                    <= validation.transaction_date.max() < evaluation.transaction_date.min()):
                raise AssertionError("Los períodos se solapan.")
            observed_ratio = train.is_fraud.sum() / (len(train) - train.is_fraud.sum())
            if observed_ratio >= config["sampling_ratio"]:
                raise ValueError("La prevalencia de entrenamiento excede el ratio propuesto; revisar el protocolo antes de comparar.")
            assignment = pd.concat([pd.DataFrame({"transaction_id": data.iloc[fold[name]].transaction_id,
                                                  "partition": name})
                                     for name in ["train", "validation", "evaluation"]])
            write_csv(out / f"particiones_{year}.csv.gz", assignment)
            for strategy in STRATEGIES:
                print(f"Evaluación {year}: entrenando {strategy}...", flush=True)
                started = time.perf_counter()
                model = build_pipeline(strategy, config["sampling_ratio"], config["trees"], config["jobs"])
                model.fit(train[NUMERIC + CATEGORICAL], train.is_fraud)
                fit_seconds = time.perf_counter() - started
                model_path = out / f"modelo_{year}_{strategy}.joblib"
                joblib.dump(model, model_path, compress=3)
                fitted_rows.append({"evaluation_year": year, "strategy": strategy,
                                    "fit_seconds": fit_seconds, "model_sha256": sha256(model_path),
                                    "train_rows": len(train), "train_frauds": int(train.is_fraud.sum())})
                p_validation = predict_chunks(model, validation[NUMERIC + CATEGORICAL])
                curve = threshold_curve(validation.is_fraud, p_validation)
                write_csv(out / f"curva_validacion_{year - 1}_{strategy}.csv.gz", curve)
                curves[(year, strategy)] = curve
                chosen, max_f1 = {}, curve.sort_values(["f1", "alerts", "threshold"], ascending=[False, True, False]).iloc[0]
                for cost_fn in COST_RATIOS:
                    chosen[cost_fn] = select_threshold(curve, cost_fn)
                    choice = chosen[cost_fn]
                    candidate_rows.append({"evaluation_year": year, "strategy": strategy, "cost_fn": cost_fn, **choice})
                    for budget in [10, 25, 50, 100, 250]:
                        capacity_choice = select_threshold(curve, cost_fn, budget)
                        budget_rows.append({"evaluation_year": year, "strategy": strategy, "cost_fn": cost_fn,
                                            "hypothetical_alert_budget_per_10000": budget, **capacity_choice})
                # El umbral de cada escenario ya está fijado antes de predecir el período posterior.
                write_json(out / f"umbrales_{year}_{strategy}.json",
                           {"cost": chosen, "f1_reference": float(max_f1.threshold),
                            "selection_period": year - 1, "evaluation_period": year})
                p_evaluation = predict_chunks(model, evaluation[NUMERIC + CATEGORICAL])
                for name, group, predictions in [("validation", validation, p_validation),
                                                 ("evaluation", evaluation, p_evaluation)]:
                    write_csv(out / f"predicciones_{year}_{strategy}_{name}.csv.gz",
                              pd.DataFrame({"transaction_id": group.transaction_id.to_numpy(),
                                            "is_fraud": group.is_fraud.to_numpy(), "score": predictions}))
                ap = float(average_precision_score(evaluation.is_fraud, p_evaluation))
                auc = float(roc_auc_score(evaluation.is_fraud, p_evaluation))
                for cost_fn in COST_RATIOS:
                    policies = {"costo": chosen[cost_fn]["threshold"], "f1_validacion": float(max_f1.threshold),
                                "referencia_007217143": 0.07217143}
                    for policy, threshold in policies.items():
                        measured = at_threshold(evaluation.is_fraud, p_evaluation, threshold)
                        results.append({"evaluation_year": year, "strategy": strategy, "policy": policy,
                                        "cost_fn": cost_fn, "cost_fp": 1, "threshold": threshold, **measured,
                                        "cost": measured["fp"] + cost_fn * measured["fn"],
                                        "cost_per_10000": (measured["fp"] + cost_fn * measured["fn"]) / measured["rows"] * 10000,
                                        "average_precision": ap, "roc_auc": auc})
                del model
                gc.collect()
                pd.DataFrame(results).to_csv(out / "comparacion_temporal.csv", index=False)
                pd.DataFrame(fitted_rows).to_csv(out / "modelos_y_tiempos.csv", index=False)
        candidates = pd.DataFrame(candidate_rows)
        candidates.to_csv(out / "seleccion_por_validacion.csv", index=False)
        pd.DataFrame(budget_rows).to_csv(out / "capacidad_hipotetica_validacion.csv", index=False)
        # Ganador por escenario y ventana decidido SOLO con el costo de validación.
        winners = candidates.sort_values(["cost", "alerts", "strategy"]).groupby(
            ["evaluation_year", "cost_fn"], as_index=False).head(1)
        winners.to_csv(out / "candidatos_para_decidir.csv", index=False)
        results_df = pd.DataFrame(results)
        aggregate = []
        for (strategy, policy, cost_fn), group in results_df.groupby(["strategy", "policy", "cost_fn"]):
            m = metrics_counts(group.tp.sum(), group.fp.sum(), group.fn.sum(), group.tn.sum())
            aggregate.append({"strategy": strategy, "policy": policy, "cost_fn": int(cost_fn), **m,
                              "cost": m["fp"] + cost_fn * m["fn"],
                              "cost_per_10000": 10000 * (m["fp"] + cost_fn * m["fn"]) / m["rows"]})
        pd.DataFrame(aggregate).to_csv(out / "resumen_historico_descriptivo.csv", index=False)
        render_plots(out, curves, results_df)
        write_json(out / "estado.json", {"status": "completed_historical_study", "folds": len(folds),
                                         "fits": len(fitted_rows), "final_model_selected": False,
                                         "independent_final_test_evaluated": False})
    except Exception as exc:
        write_json(out / "estado.json", {"status": "failed", "error": str(exc), "completed_fits": len(fitted_rows)})
        raise
    print(f"Estudio histórico listo en {out}. La selección queda para revisión.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["profile", "run"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("resultados_finan"))
    parser.add_argument("--last-folds", type=int, default=3)
    parser.add_argument("--min-positives", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=-1)
    args = parser.parse_args()
    data = normalize(pd.read_csv(args.data))
    if args.action == "profile":
        print(profile(data).to_string(index=False))
        folds, _ = temporal_folds(data, args.last_folds, args.min_positives)
        print(f"Ventanas viables: {len(folds)}. Se requieren al menos dos para el estudio.")
        return
    info = json.loads(Path(str(args.data) + ".json").read_text(encoding="utf-8"))
    if info.get("file_sha256") != sha256(args.data):
        raise ValueError("El archivo no coincide con su manifiesto de extracción.")
    if info.get("test_excluded") is not True or info.get("status") != "development_only":
        raise ValueError("Se requiere la exportación de desarrollo que excluye el test S9.")
    if info.get("excluded_test_ids_sha256") != "3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08":
        raise ValueError("No coincide la partición S9 excluida.")
    if len(data) != 841721 or int(data.is_fraud.sum()) != 1201:
        raise ValueError("El archivo no corresponde al desarrollo S9 completo.")
    if args.last_folds < 2 or args.min_positives < 6:
        raise ValueError("Se requieren >=2 ventanas y >=6 positivos por segmento.")
    config = {"last_folds": args.last_folds, "min_positives": args.min_positives,
              "sampling_ratio": 0.1, "trees": 200, "jobs": args.jobs}
    run_study(data, args.output.resolve(), config, info)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"ERROR: {exc}")
