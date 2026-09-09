"""Recalcula decisiones de negocio con predicciones guardadas; no entrena.

python src/evaluation/seguimiento/costos/analizar_costos.py preparar
python src/evaluation/seguimiento/costos/analizar_costos.py seleccionar
python src/evaluation/seguimiento/costos/analizar_costos.py evaluar
"""
from __future__ import annotations

import os
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

WORK = Path(os.environ.get('FINAN_EXPERIMENT_DIR', 'data/experimentos')).resolve()
ROOT = WORK / 'finan_decision_costos'
INPUT = ROOT / "insumos"
OUT = ROOT / "resultados"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, frame):
    content = frame.to_csv(index=False).encode("utf-8")
    if str(path).endswith(".gz"): content = gzip.compress(content, compresslevel=6, mtime=0)
    Path(path).write_bytes(content)


def config():
    return json.loads((ROOT / "protocolo.json").read_text(encoding="utf-8"))


def prepare():
    """Copia insumos ya verificados. No abre predicciones para seleccionar."""
    INPUT.mkdir(parents=True, exist_ok=False)
    OUT.mkdir(parents=True, exist_ok=False)
    cfg = config()
    data_path = WORK / "finan_datos_recibidos/finan_desarrollo.csv.gz"
    assert data_path.is_file()
    manifest = json.loads(Path(str(data_path) + ".json").read_text())
    assert manifest["test_excluded"] is True
    assert sha(data_path) == manifest["file_sha256"]
    assert manifest["excluded_test_ids_sha256"] == "3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08"
    data = pd.read_csv(data_path, usecols=["transaction_id", "transaction_date", "amount", "is_fraud"], float_precision="round_trip")
    assert data.transaction_id.is_unique and len(data) == cfg["development_rows"]
    assert data.is_fraud.isin([0, 1]).all() and data.is_fraud.sum() == cfg["development_frauds"]
    assert np.isfinite(data.amount).all()
    write_csv(INPUT / "desarrollo_minimo.csv.gz", data)
    shutil.copy2(Path(str(data_path) + ".json"), INPUT / "manifiesto_desarrollo_original.json")
    previous = WORK / "finan_ronda3/experimento"
    hashes = json.loads((previous / "integridad_predicciones.json").read_text())
    assert len(hashes) == 78
    for item in hashes:
        source = previous / item["file"]
        assert sha(source) == item["sha256"]
        shutil.copy2(source, INPUT / source.name)
    dates = pd.to_datetime(data.transaction_date)
    training = []
    for win in cfg["windows"]:
        frauds = data[(dates < win["validation_start"]) & (data.is_fraud == 1)]
        amounts = frauds.amount.clip(lower=0)
        training.append({"evaluation_year": win["year"], "training_end_exclusive": win["validation_start"],
                         "training_frauds": len(frauds), "negative_amount_frauds": int((frauds.amount < 0).sum()),
                         "positive_exposure_mean": float(amounts.mean()), "positive_exposure_median": float(amounts.median()),
                         "positive_exposure_sum": float(amounts.sum())})
    write_csv(INPUT / "referencia_importes_entrenamiento.csv", pd.DataFrame(training))
    write_json(INPUT / "procedencia.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
               "source_development_sha256": sha(data_path), "s9_excluded": True,
               "minimal_development_sha256": sha(INPUT / "desarrollo_minimo.csv.gz"),
               "source_prediction_manifest_sha256": sha(previous / "integridad_predicciones.json"),
               "prediction_hashes": hashes,
               "minimal_columns": list(data.columns), "rows": len(data),
               "input_hashes": {p.name: sha(p) for p in INPUT.iterdir() if p.is_file()}})
    print("Insumos preparados: 841.721 IDs de desarrollo, 78 predicciones y medias anteriores a validación.", flush=True)


def curve_from_predictions(pred, amounts):
    y = pred.is_fraud.to_numpy(dtype=np.int8)
    scores = pred.score.to_numpy(dtype=float)
    assert len(y) and np.isin(y, [0, 1]).all() and y.sum() > 0
    assert np.isfinite(scores).all() and np.logical_and(scores >= 0, scores <= 1).all()
    order = np.argsort(-scores, kind="stable")
    sorted_scores = scores[order]
    ends = np.r_[np.flatnonzero(sorted_scores[1:] != sorted_scores[:-1]), len(y) - 1]
    tp = np.r_[0, np.cumsum(y[order], dtype=np.int64)[ends]]
    alerts = np.r_[0, ends + 1]
    exposure = np.maximum(np.asarray(amounts), 0) * y
    detected_exposure = np.r_[0.0, np.cumsum(exposure[order])[ends]]
    missed_exposure = np.maximum(0.0, exposure.sum() - detected_exposure)
    missed_exposure[-1] = 0.0
    return pd.DataFrame({"threshold": np.r_[np.nextafter(1.0, 2.0), sorted_scores[ends]],
                         "tp": tp, "fp": alerts - tp, "fn": y.sum() - tp,
                         "tn": len(y) - y.sum() - alerts + tp, "alerts": alerts, "rows": len(y),
                         "recall": tp / y.sum(), "precision": np.divide(tp, alerts, out=np.zeros(len(tp)), where=alerts > 0),
                         "f1": 2 * tp / (alerts + y.sum()), "alerts_per_10000": alerts * 10000 / len(y),
                         "fn_positive_exposure": missed_exposure})


def min_choice(curve, review_cost, fn_cost, cap, variable_fraction=None):
    costs = (curve.alerts.to_numpy() * review_cost +
             (curve.fn.to_numpy() * fn_cost if variable_fraction is None else curve.fn_positive_exposure.to_numpy() * variable_fraction))
    eligible = np.flatnonzero(curve.alerts_per_10000.to_numpy() <= cap)
    # Curve is ordered by increasing alerts; argmin retains fewer alerts at ties.
    idx = eligible[np.argmin(costs[eligible])]
    return {**curve.iloc[idx].to_dict(), "validation_cost": float(costs[idx])}


def parameters(cfg, mean, hour=None, fraction=None, cap=None):
    hour = cfg["base_hourly_review_cost"] if hour is None else hour
    fraction = cfg["base_avoidable_fraction"] if fraction is None else fraction
    cap = cfg["base_alert_capacity_per_10000"] if cap is None else cap
    return {"hourly_review_cost": hour, "review_cost": hour * cfg["review_minutes"] / 60,
            "avoidable_fraction": fraction, "fn_cost": mean * fraction,
            "training_fraud_positive_exposure_mean": mean, "capacity_per_10000": cap,
            "cost_method": "fixed_training_mean"}


def select():
    """Solo abre predicciones de validación. Guarda decisiones antes de evaluar."""
    cfg = config()
    assert not (OUT / "decisiones_validacion.csv").exists(), "Use una carpeta de resultados nueva para repetir."
    source = json.loads((INPUT / "procedencia.json").read_text())
    assert sha(INPUT / "desarrollo_minimo.csv.gz") == source["minimal_development_sha256"]
    data = pd.read_csv(INPUT / "desarrollo_minimo.csv.gz", float_precision="round_trip").set_index("transaction_id")
    data.transaction_date = pd.to_datetime(data.transaction_date)
    means = pd.read_csv(INPUT / "referencia_importes_entrenamiento.csv").set_index("evaluation_year")
    candidates = sorted(p.name.split("_", 2)[2].removesuffix("_validation.csv.gz") for p in INPUT.glob("predicciones_2019_*_validation.csv.gz"))
    assert len(candidates) == 13
    hashes = {x["file"]: x["sha256"] for x in source["prediction_hashes"]}
    decisions, candidate_rows, frontiers = [], [], []
    counter = 0

    def save(year, policy, name, choice, pars, **extras):
        nonlocal counter
        counter += 1
        value = {"decision_id": f"D{counter:05d}", "evaluation_year": year, "policy": policy,
                 "candidate": name, **pars, "threshold": float(choice["threshold"]),
                 **{f"validation_{key}": float(choice[key]) for key in ["tp", "fp", "fn", "tn", "rows", "alerts", "recall", "precision", "f1", "alerts_per_10000", "fn_positive_exposure"]},
                 "validation_cost": float(choice.get("validation_cost", pars["review_cost"] * choice["alerts"] + pars["fn_cost"] * choice["fn"])),
                 **extras}
        decisions.append(value)
        return value

    for win in cfg["windows"]:
        year = win["year"]
        valid = data[(data.transaction_date >= win["validation_start"]) & (data.transaction_date < win["validation_end_exclusive"])]
        mean = float(means.loc[year, "positive_exposure_mean"])
        measured_mean = data.loc[(data.transaction_date < win["validation_start"]) & (data.is_fraud == 1), "amount"].clip(lower=0).mean()
        assert abs(mean - measured_mean) < 1e-10
        base = parameters(cfg, mean)
        curves = {}
        for name in candidates:
            path = INPUT / f"predicciones_{year}_{name}_validation.csv.gz"
            assert sha(path) == hashes[path.name]
            pred = pd.read_csv(path, float_precision="round_trip")
            assert pred.transaction_id.is_unique and set(pred.transaction_id) == set(valid.index)
            aligned = valid.loc[pred.transaction_id]
            assert np.array_equal(pred.is_fraud.to_numpy(), aligned.is_fraud.to_numpy())
            curves[name] = curve_from_predictions(pred, aligned.amount.to_numpy())
            write_csv(OUT / f"curva_validacion_{year}_{name}.csv.gz", curves[name])

        def cost_winner(pars, cap=None, variable=False, record=False):
            cap = pars["capacity_per_10000"] if cap is None else cap
            rows = []
            for name, curve in curves.items():
                ch = min_choice(curve, pars["review_cost"], pars["fn_cost"], cap, pars["avoidable_fraction"] if variable else None)
                rows.append({"candidate": name, **ch})
                if record: candidate_rows.append({"evaluation_year": year, **pars, **rows[-1]})
            return min(rows, key=lambda x: (x["validation_cost"], x["alerts"], x["candidate"], -x["threshold"]))

        # Entire predefined sensitivity grid; not a hyperparameter search.
        for hour in cfg["sensitivity_hourly_costs"]:
            for fraction in cfg["sensitivity_avoidable_fractions"]:
                for cap in cfg["sensitivity_capacities_per_10000"]:
                    pars = parameters(cfg, mean, hour, fraction, cap)
                    chosen = cost_winner(pars, record=True)
                    is_base = hour == cfg["base_hourly_review_cost"] and fraction == cfg["base_avoidable_fraction"] and cap == cfg["base_alert_capacity_per_10000"]
                    save(year, "cost_sensitivity", chosen["candidate"], chosen, pars, is_base=is_base)

        best = cost_winner(base)
        chosen_model = best["candidate"]
        same = curves[chosen_model]
        save(year, "base_min_cost_capacity", chosen_model, best, base)
        unconstrained = cost_winner(base, cap=10000)
        save(year, "base_min_cost_unconstrained", unconstrained["candidate"], unconstrained, {**base, "capacity_per_10000": 10000})
        f1_pool = []
        for name, curve in curves.items():
            ch = curve.sort_values(["f1", "alerts", "threshold"], ascending=[False, True, False]).iloc[0].to_dict()
            f1_pool.append({"candidate": name, **ch})
        f1 = min(f1_pool, key=lambda x: (-x["f1"], x["alerts"], x["candidate"], -x["threshold"]))
        save(year, "f1_pool_reference", f1["candidate"], f1, base)
        f1_same = next(row for row in f1_pool if row["candidate"] == chosen_model)
        save(year, "f1_same_model_reference", chosen_model, f1_same, base)
        # A fixed 0.5 threshold and no/all-alert references are never tuned.
        half = same[same.threshold >= 0.5].iloc[-1].to_dict()
        half["threshold"] = 0.5
        save(year, "threshold_0_5_same_model", chosen_model, half, base)
        save(year, "no_alert_reference", chosen_model, same.iloc[0].to_dict(), base)
        all_alert = same.iloc[-1].to_dict(); all_alert["threshold"] = 0.0
        save(year, "all_alert_reference", chosen_model, all_alert, base)

        # Frontier for the same model and for all candidates, with and without a cost ceiling.
        for cap in cfg["sensitivity_capacities_per_10000"]:
            pars = parameters(cfg, mean, cap=cap)
            for pool_name, pool in [("same_model", {chosen_model: same}), ("all_candidates", curves)]:
                for economic in [False, True]:
                    best_rows = []
                    for name, curve in pool.items():
                        costs = pars["review_cost"] * curve.alerts + pars["fn_cost"] * curve.fn
                        feasible = curve.alerts_per_10000 <= cap
                        if economic: feasible &= costs <= pars["fn_cost"] * (curve.tp + curve.fn) + 1e-9
                        ch = curve[feasible].sort_values(["tp", "fp", "threshold"], ascending=[False, True, False]).iloc[0].to_dict()
                        ch["validation_cost"] = ch["alerts"] * pars["review_cost"] + ch["fn"] * pars["fn_cost"]
                        best_rows.append({"candidate": name, **ch})
                    winner = min(best_rows, key=lambda x: (-x["tp"], x["fp"], x["candidate"], -x["threshold"]))
                    save(year, f"frontier_{pool_name}_{'economic' if economic else 'capacity_only'}", winner["candidate"], winner, pars)

        # Data-amount-dependent sensitivity, clearly separated from the primary fixed matrix.
        for fraction in cfg["sensitivity_avoidable_fractions"]:
            pars = parameters(cfg, mean, fraction=fraction)
            pars["cost_method"] = "variable_positive_amount"
            chosen = cost_winner(pars, variable=True)
            save(year, "variable_amount_sensitivity", chosen["candidate"], chosen, pars)

        # Complete nondominated TP/alerts frontier of the primary candidate in validation.
        frontier = same.sort_values(["tp", "alerts", "threshold"], ascending=[True, True, False]).drop_duplicates("tp").copy()
        frontier["evaluation_year"] = year
        frontier["candidate"] = chosen_model
        frontier["review_cost"] = base["review_cost"]
        frontier["fn_cost"] = base["fn_cost"]
        frontier["review_hours_per_10000"] = frontier.alerts_per_10000 * cfg["review_minutes"] / 60
        frontier["cost"] = frontier.alerts * base["review_cost"] + frontier.fn * base["fn_cost"]
        frontier["saving_vs_no_alert"] = frontier.tp * base["fn_cost"] - frontier.alerts * base["review_cost"]
        frontier["additional_tp"] = frontier.tp.diff()
        frontier["additional_alerts"] = frontier.alerts.diff()
        frontier["break_even_loss_per_added_fraud"] = frontier.additional_alerts / frontier.additional_tp * base["review_cost"]
        frontiers.append(frontier)

    frame = pd.DataFrame(decisions)
    write_csv(OUT / "decisiones_validacion.csv", frame)
    write_csv(OUT / "comparacion_candidatos_validacion.csv", pd.DataFrame(candidate_rows))
    write_csv(OUT / "frontera_completa_validacion.csv", pd.concat(frontiers, ignore_index=True))
    lock = {"selected_utc": datetime.now(timezone.utc).isoformat(), "protocol_sha256": sha(ROOT / "protocolo.json"),
            "decision_sha256": sha(OUT / "decisiones_validacion.csv"), "decisions": len(frame),
            "selection_inputs": "validation predictions and earlier training-amount statistics only",
            "prior_evaluation_exploration_acknowledged": True,
            "independent_final_test": False, "new_fits": 0}
    write_json(OUT / "seleccion_fijada.json", lock)
    print(f"Fijadas {len(frame)} decisiones con validación; ninguna predicción de evaluación se abrió en esta etapa.", flush=True)


def measure(frame, selected, dates, amounts, minutes):
    y = frame.is_fraud.to_numpy()
    pred = frame.score.to_numpy() >= selected["threshold"]
    tp, fp = int(np.sum(pred & (y == 1))), int(np.sum(pred & (y == 0)))
    fn, tn = int(np.sum(~pred & (y == 1))), int(np.sum(~pred & (y == 0)))
    alerts = tp + fp
    exposure = np.maximum(np.asarray(amounts), 0) * y
    missed = float(exposure[~pred].sum())
    loss = selected["fn_cost"] * fn if selected["cost_method"] == "fixed_training_mean" else selected["avoidable_fraction"] * missed
    no_alert_loss = selected["fn_cost"] * int(y.sum()) if selected["cost_method"] == "fixed_training_mean" else selected["avoidable_fraction"] * exposure.sum()
    cost = selected["review_cost"] * alerts + loss
    rate = 10000 * alerts / len(y)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "rows": len(y), "alerts": alerts,
            "recall": tp / (tp + fn), "precision": tp / alerts if alerts else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn), "alerts_per_10000": rate,
            "fp_per_10000": fp * 10000 / len(y), "review_hours_per_10000": rate * minutes / 60,
            "review_hours_total": alerts * minutes / 60, "cost": float(cost), "no_alert_cost": float(no_alert_loss),
            "saving_vs_no_alert": float(no_alert_loss - cost),
            "saving_fraction": float((no_alert_loss - cost) / no_alert_loss) if no_alert_loss else 0.0,
            "capacity_exceeded": bool(rate > selected["capacity_per_10000"] + 1e-10),
            "more_costly_than_no_alert": bool(cost > no_alert_loss + 1e-9),
            "fn_positive_exposure": missed}


def evaluate():
    cfg = config()
    assert not (OUT / "evaluacion_decisiones.csv").exists(), "La evaluación ya existe."
    lock = json.loads((OUT / "seleccion_fijada.json").read_text())
    assert sha(ROOT / "protocolo.json") == lock["protocol_sha256"]
    assert sha(OUT / "decisiones_validacion.csv") == lock["decision_sha256"]
    source = json.loads((INPUT / "procedencia.json").read_text())
    hashes = {x["file"]: x["sha256"] for x in source["prediction_hashes"]}
    decisions = pd.read_csv(OUT / "decisiones_validacion.csv", float_precision="round_trip")
    data = pd.read_csv(INPUT / "desarrollo_minimo.csv.gz", float_precision="round_trip").set_index("transaction_id")
    data.transaction_date = pd.to_datetime(data.transaction_date)
    results, monthly = [], []
    for (year, name), choices in decisions.groupby(["evaluation_year", "candidate"], sort=True):
        path = INPUT / f"predicciones_{year}_{name}_evaluation.csv.gz"
        assert sha(path) == hashes[path.name]
        frame = pd.read_csv(path, float_precision="round_trip")
        expected = data[data.transaction_date.dt.year == year]
        assert frame.transaction_id.is_unique and set(frame.transaction_id) == set(expected.index)
        aligned = expected.loc[frame.transaction_id]
        assert np.array_equal(frame.is_fraud.to_numpy(), aligned.is_fraud.to_numpy())
        for selected in choices.to_dict("records"):
            metrics = measure(frame, selected, aligned.transaction_date, aligned.amount, cfg["review_minutes"])
            results.append({**selected, **{f"evaluation_{k}": v for k, v in metrics.items()}})
            if selected["policy"] in ["base_min_cost_capacity", "f1_same_model_reference"]:
                months = aligned.transaction_date.dt.to_period("M").astype(str).to_numpy()
                for month in sorted(set(months)):
                    mask = months == month
                    p = frame.loc[mask]
                    g = aligned.loc[mask]
                    # No positive support in a month: recall is undefined, not evidence of no missed fraud.
                    positives = int(p.is_fraud.sum())
                    alerts = p.score.to_numpy() >= selected["threshold"]
                    tp = int(np.sum(alerts & (p.is_fraud.to_numpy() == 1)))
                    fp = int(np.sum(alerts & (p.is_fraud.to_numpy() == 0)))
                    rate = 10000 * (tp + fp) / len(p)
                    monthly.append({"decision_id": selected["decision_id"], "evaluation_year": year,
                                    "candidate": name, "policy": selected["policy"], "month": month,
                                    "rows": len(p), "frauds": positives, "tp": tp, "fp": fp,
                                    "recall": tp / positives if positives else np.nan,
                                    "alerts_per_10000": rate, "review_hours_per_10000": rate * cfg["review_minutes"] / 60,
                                    "capacity_exceeded": bool(rate > selected["capacity_per_10000"] + 1e-10)})
    output = pd.DataFrame(results).sort_values("decision_id")
    write_csv(OUT / "evaluacion_decisiones.csv", output)
    write_csv(OUT / "carga_mensual.csv", pd.DataFrame(monthly))
    write_csv(OUT / "resumen_decision_base.csv", output[output.policy.isin(["base_min_cost_capacity", "f1_same_model_reference", "f1_pool_reference"])])
    write_json(OUT / "estado.json", {"status": "completed", "completed_utc": datetime.now(timezone.utc).isoformat(),
               "new_fits": 0, "evaluated_decisions": len(output), "selection_file_unchanged": sha(OUT / "decisiones_validacion.csv") == lock["decision_sha256"],
               "official_model_replaced": False, "s9_test_excluded": True, "independent_final_test": False})
    print("Evaluación terminada sin cambiar las decisiones fijadas.", flush=True)
    columns = ["evaluation_year", "policy", "candidate", "threshold", "fn_cost", "evaluation_tp", "evaluation_fp", "evaluation_recall", "evaluation_cost", "evaluation_saving_vs_no_alert", "evaluation_alerts_per_10000"]
    print(output[output.policy.isin(["base_min_cost_capacity", "f1_same_model_reference", "f1_pool_reference"])][columns].to_string(index=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["preparar", "seleccionar", "evaluar"])
    args = parser.parse_args()
    {"preparar": prepare, "seleccionar": select, "evaluar": evaluate}[args.stage]()
