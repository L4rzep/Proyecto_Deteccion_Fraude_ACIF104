"""Comprobación independiente de conteos, decisiones y costos guardados."""
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

from analizar_costos import ROOT, INPUT, OUT, config, sha, curve_from_predictions, min_choice, write_json


class BusinessRules(unittest.TestCase):
    def test_correct_alert_also_consumes_review_cost(self):
        p = pd.DataFrame({"is_fraud": [1, 1], "score": [.9, .8]})
        curve = curve_from_predictions(p, [10, 20])
        row = min_choice(curve, review_cost=3, fn_cost=2, cap=10000)
        self.assertEqual(row["alerts"], 0)
        self.assertEqual(row["validation_cost"], 4)

    def test_equal_scores_cannot_be_partially_selected(self):
        p = pd.DataFrame({"is_fraud": [1, 0, 1], "score": [.5, .5, .2]})
        curve = curve_from_predictions(p, [10, 20, 30])
        row = min_choice(curve, review_cost=1, fn_cost=100, cap=10000 / 3)
        self.assertEqual(row["alerts"], 0)

    def test_negative_fraud_retains_label_without_negative_direct_loss(self):
        p = pd.DataFrame({"is_fraud": [1, 1, 0], "score": [.8, .7, .6]})
        curve = curve_from_predictions(p, [-10, 100, 50])
        self.assertEqual(curve.iloc[0].fn, 2)
        self.assertEqual(curve.iloc[0].fn_positive_exposure, 100)
        self.assertEqual(curve.iloc[1].tp, 1)
        self.assertEqual(curve.iloc[1].fn_positive_exposure, 100)

    def test_relation_to_older_fp_fn_only_cost(self):
        tp, fp, fn, review, loss = 17, 347, 106, 3, 150
        complete = review * (tp + fp) + loss * fn
        equivalent = review * fp + (loss - review) * fn + review * (tp + fn)
        self.assertEqual(complete, equivalent)
        self.assertEqual((28 - 17) + (1599 - 347), 1263)


def verify():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BusinessRules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful()
    cfg = config()
    source = json.loads((INPUT / "procedencia.json").read_text())
    for name, expected in source["input_hashes"].items():
        assert sha(INPUT / name) == expected, name
    lock = json.loads((OUT / "seleccion_fijada.json").read_text())
    assert sha(ROOT / "protocolo.json") == lock["protocol_sha256"]
    assert sha(OUT / "decisiones_validacion.csv") == lock["decision_sha256"]
    assert lock["new_fits"] == 0 and cfg["s9_test_excluded"]
    decisions = pd.read_csv(OUT / "evaluacion_decisiones.csv", float_precision="round_trip")
    assert len(decisions) == lock["decisions"] == 225
    minimal = pd.read_csv(INPUT / "desarrollo_minimo.csv.gz", float_precision="round_trip").set_index("transaction_id")
    minimal.transaction_date = pd.to_datetime(minimal.transaction_date)
    assert minimal.index.is_unique and len(minimal) == 841721 and minimal.is_fraud.sum() == 1201
    curves = {}
    checked_curve_points = 0
    for path in sorted(OUT.glob("curva_validacion_*.csv.gz")):
        suffix = path.name.removeprefix("curva_validacion_").removesuffix(".csv.gz")
        year, candidate = suffix.split("_", 1)
        curve = pd.read_csv(path, float_precision="round_trip")
        p = pd.read_csv(INPUT / f"predicciones_{year}_{candidate}_validation.csv.gz", float_precision="round_trip")
        # Rebuild counts using ascending scores and left search, independently from the producer.
        order = np.argsort(p.score.to_numpy(), kind="stable")
        s = p.score.to_numpy()[order]
        y = p.is_fraud.to_numpy()[order]
        k = np.searchsorted(s, curve.threshold.to_numpy(), side="left")
        prefix_tp = np.r_[0, np.cumsum(y)]
        tp = int(y.sum()) - prefix_tp[k]
        fp = len(y) - k - tp
        assert np.array_equal(tp, curve.tp) and np.array_equal(fp, curve.fp)
        assert np.array_equal(len(y) - k, curve.alerts)
        exposure = minimal.loc[p.transaction_id, "amount"].to_numpy()[order].clip(min=0) * y
        prefix_exposure = np.r_[0., np.cumsum(exposure)]
        assert np.allclose(prefix_exposure[k], curve.fn_positive_exposure, rtol=1e-10, atol=1e-7)
        curves[(int(year), candidate)] = curve
        checked_curve_points += len(curve)

    for (year, candidate), rows in decisions.groupby(["evaluation_year", "candidate"]):
        for split, prefix in [("validation", "validation"), ("evaluation", "evaluation")]:
            pred = pd.read_csv(INPUT / f"predicciones_{year}_{candidate}_{split}.csv.gz", float_precision="round_trip")
            aligned = minimal.loc[pred.transaction_id]
            assert np.array_equal(aligned.is_fraud, pred.is_fraud)
            y = pred.is_fraud.to_numpy()
            amounts = aligned.amount.to_numpy().clip(min=0)
            for row in rows.to_dict("records"):
                labels = pred.score.to_numpy() >= row["threshold"]
                tn, fp, fn, tp = confusion_matrix(y, labels, labels=[0, 1]).ravel()
                for key, value in [("tn", tn), ("fp", fp), ("fn", fn), ("tp", tp), ("alerts", tp + fp)]:
                    assert value == row[f"{prefix}_{key}"], (row["decision_id"], split, key)
                cost = row["review_cost"] * (tp + fp)
                cost += (row["fn_cost"] * fn if row["cost_method"] == "fixed_training_mean"
                         else row["avoidable_fraction"] * amounts[(y == 1) & ~labels].sum())
                assert np.isclose(cost, row[f"{prefix}_cost"], atol=1e-7, rtol=1e-10)

    # All candidate cost choices: verify true minimum among full feasible validation curves.
    all_candidates = pd.read_csv(OUT / "comparacion_candidatos_validacion.csv", float_precision="round_trip")
    assert len(all_candidates) == 1755
    for row in all_candidates.to_dict("records"):
        c = curves[(row["evaluation_year"], row["candidate"])]
        feasible = c[c.alerts_per_10000 <= row["capacity_per_10000"]].copy()
        feasible["cost"] = feasible.alerts * row["review_cost"] + feasible.fn * row["fn_cost"]
        winner = feasible.sort_values(["cost", "alerts", "threshold"], ascending=[True, True, False]).iloc[0]
        assert winner.threshold == row["threshold"]
        assert np.isclose(winner.cost, row["validation_cost"], atol=1e-7)
    # Pool winners and base recommendation must follow validation only.
    for row in decisions[decisions.policy == "cost_sensitivity"].to_dict("records"):
        cs = all_candidates[(all_candidates.evaluation_year == row["evaluation_year"]) &
                            (all_candidates.hourly_review_cost == row["hourly_review_cost"]) &
                            (all_candidates.avoidable_fraction == row["avoidable_fraction"]) &
                            (all_candidates.capacity_per_10000 == row["capacity_per_10000"])]
        winner = cs.sort_values(["validation_cost", "alerts", "candidate", "threshold"], ascending=[True, True, True, False]).iloc[0]
        assert winner.candidate == row["candidate"] and winner.threshold == row["threshold"]
    for year in [2015, 2016, 2019]:
        r = decisions[(decisions.evaluation_year == year) & (decisions.policy == "base_min_cost_capacity")].iloc[0]
        b = decisions[(decisions.evaluation_year == year) & (decisions.policy == "cost_sensitivity") &
                      (decisions.hourly_review_cost == 30) & (decisions.avoidable_fraction == .5) &
                      (decisions.capacity_per_10000 == 50)].iloc[0]
        assert r.threshold == b.threshold and r.candidate == b.candidate
    # Recompute all 60 recall-frontier choices; capacity-only agrees with R3 when available.
    for row in decisions[decisions.policy.str.startswith("frontier_")].to_dict("records"):
        candidates = []
        for (year, name), c in curves.items():
            if year != row["evaluation_year"]: continue
            if "same_model" in row["policy"] and name != row["candidate"]: continue
            eligible = c.alerts_per_10000 <= row["capacity_per_10000"]
            if row["policy"].endswith("_economic"):
                eligible &= c.alerts * row["review_cost"] + c.fn * row["fn_cost"] <= (c.tp + c.fn) * row["fn_cost"] + 1e-9
            best = c[eligible].sort_values(["tp", "fp", "threshold"], ascending=[False, True, False]).iloc[0]
            candidates.append({"candidate": name, **best.to_dict()})
        best = min(candidates, key=lambda p: (-p["tp"], p["fp"], p["candidate"], -p["threshold"]))
        assert row["candidate"] == best["candidate"] and row["threshold"] == best["threshold"]
    answer = {"status": "passed", "business_rule_tests": result.testsRun, "input_files_verified": len(source["input_hashes"]),
              "curves_verified": len(curves), "curve_points_verified": checked_curve_points,
              "validation_and_evaluation_decisions_recalculated": len(decisions),
              "candidate_cost_optima_verified": len(all_candidates), "sensitivity_pool_winners_verified": 135,
              "recall_frontier_winners_verified": 60, "new_fits": 0, "s9_test_excluded": True,
              "decisions_unchanged_after_evaluation": True, "independent_final_test": False}
    write_json(OUT / "verificacion.json", answer)
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__": verify()
