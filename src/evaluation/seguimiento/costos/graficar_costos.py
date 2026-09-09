"""Reproduce tres figuras y la carga mensual complementaria desde decisiones verificadas."""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

from analizar_costos import ROOT, WORK, INPUT, OUT, config, sha, write_csv, write_json


def num(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def run():
    cfg = config()
    verify = json.loads((OUT / "verificacion.json").read_text())
    assert verify["status"] == "passed"
    results = pd.read_csv(OUT / "evaluacion_decisiones.csv", float_precision="round_trip")
    selected = results[results.policy == "base_min_cost_capacity"].set_index("evaluation_year")
    base = selected.loc[2019]
    same_f1 = results[(results.evaluation_year == 2019) & (results.policy == "f1_same_model_reference")].iloc[0]
    pool_f1 = results[(results.evaluation_year == 2019) & (results.policy == "f1_pool_reference")].iloc[0]
    frontier = results[(results.evaluation_year == 2019) & (results.policy == "frontier_same_model_capacity_only")].sort_values("capacity_per_10000")
    edge = frontier[frontier.capacity_per_10000 == 50].iloc[0]
    amounts = pd.read_csv(INPUT / "referencia_importes_entrenamiento.csv")
    monthly = pd.read_csv(OUT / "carga_mensual.csv")
    labels = {"rf_actualizado": "RF actualizado (R2)", "rf_variables_revisadas": "RF con variables revisadas (R2)", "rf_profundo": "RF profundo (R2)"}

    # Additional load diagnostic for the economic-recall boundary, without changing its threshold.
    data = pd.read_csv(INPUT / "desarrollo_minimo.csv.gz", float_precision="round_trip").set_index("transaction_id")
    data.transaction_date = pd.to_datetime(data.transaction_date)
    extra_monthly = []
    edges = results[(results.policy == "frontier_same_model_economic") & (results.capacity_per_10000 == 50)]
    for row in edges.to_dict("records"):
        p = pd.read_csv(INPUT / f"predicciones_{row['evaluation_year']}_{row['candidate']}_evaluation.csv.gz", float_precision="round_trip")
        p["month"] = data.loc[p.transaction_id, "transaction_date"].dt.to_period("M").astype(str).to_numpy()
        p["alert"] = p.score >= row["threshold"]
        for month, group in p.groupby("month"):
            rate = group.alert.sum() * 10000 / len(group)
            extra_monthly.append({"decision_id": row["decision_id"], "evaluation_year": row["evaluation_year"],
                                  "candidate": row["candidate"], "threshold": row["threshold"], "month": month,
                                  "rows": len(group), "alerts": int(group.alert.sum()), "alerts_per_10000": rate,
                                  "review_hours_per_10000": rate * cfg["review_minutes"] / 60,
                                  "capacity_per_10000": 50, "capacity_exceeded": bool(rate > 50)})
        summed = sum(a["alerts"] for a in extra_monthly if a["decision_id"] == row["decision_id"])
        assert summed == row["evaluation_alerts"]
    extra_monthly = pd.DataFrame(extra_monthly)
    write_csv(OUT / "carga_mensual_limite_economico.csv", extra_monthly)
    e19 = extra_monthly[extra_monthly.evaluation_year == 2019]

    figures = ROOT / "figuras"
    figures.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "figure.facecolor": "white"})
    blue, orange, grey, red = "#165D8D", "#C77C22", "#5D6872", "#AC3E40"
    c = pd.read_csv(OUT / "curva_validacion_2019_rf_actualizado.csv.gz", float_precision="round_trip")
    cost = c.alerts * base.review_cost + c.fn * base.fn_cost
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.7), gridspec_kw={"width_ratios": [1, 1.1]}, layout="constrained")
    for ax in axes:
        ax.plot(c.threshold, cost, color=blue, lw=1.5)
        ax.axhline(base.fn_cost * (base.validation_tp + base.validation_fn), color=grey, ls="--", label="No emitir alertas")
        ax.scatter([base.threshold], [base.validation_cost], s=60, color=orange, zorder=5, label="Mínimo costo en validación")
        ax.scatter([same_f1.threshold], [same_f1.validation_cost], s=44, facecolors="white", edgecolors=blue, zorder=6, label="Máximo F1 del mismo modelo")
        ax.set_xlabel("Umbral de la puntuación")
        ax.set_ylabel("Costo del período de validación (u.m.)")
        ax.grid(alpha=.16)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: num(v)))
    axes[0].set_xscale("symlog", linthresh=.0001)
    axes[0].set_yscale("log")
    axes[0].set_title("Curva completa")
    axes[1].set_xlim(.012, .055)
    axes[1].set_ylim(3750, 4900)
    axes[1].axvline(edge.threshold, color=red, ls=":", label="Máximo recall con límite 50 / 10.000")
    axes[1].set_title("Detalle: mínima diferencia frente a F1")
    axes[1].legend(loc="upper right", fontsize=8, frameon=False)
    fig.suptitle("Selección con julio–diciembre de 2018 · RF actualizado", fontsize=13, weight="bold")
    fig.savefig(figures / "curva_costo_umbral_validacion_2018.png", dpi=180)
    fig.savefig(figures / "curva_costo_umbral_validacion_2018.pdf")
    plt.close(fig)

    displayed = [same_f1, base, edge,
                 frontier[frontier.capacity_per_10000 == 100].iloc[0],
                 frontier[frontier.capacity_per_10000 == 250].iloc[0]]
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.7), layout="constrained")
    x = [r.evaluation_alerts_per_10000 for r in displayed]
    y = [r.evaluation_recall * 100 for r in displayed]
    savings = [r.evaluation_saving_vs_no_alert for r in displayed]
    axes[0].plot(x, y, "o-", color=blue, lw=1.5)
    axes[0].set_ylim(0, 28)
    axes[0].set_ylabel("Recall en 2019 (%)")
    axes[0].set_title("Detección y carga de revisión")
    for i, r in enumerate(displayed):
        axes[0].annotate(f"{int(r.evaluation_tp)} fraudes", (x[i], y[i]), textcoords="offset points",
                         xytext=[(-28, -16), (8, -4), (3, 11), (3, 11), (-30, 11)][i], fontsize=9)
    axes[1].plot(x, savings, "o-", color=orange, lw=1.5)
    axes[1].axhline(0, color=grey, ls="--")
    axes[1].set_ylabel("Ahorro frente a no alertar (u.m. del período)")
    axes[1].set_title("Beneficio bajo el escenario académico")
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: num(v)))
    axes[1].annotate(f"{int(edge.evaluation_tp)} detectados: {num(edge.evaluation_saving_vs_no_alert, 2)} u.m.", (edge.evaluation_alerts_per_10000, edge.evaluation_saving_vs_no_alert),
                     xytext=(15, 25), textcoords="offset points", fontsize=9,
                     arrowprops={"arrowstyle": "-", "color": grey})
    for ax in axes:
        ax.axvline(50, color=red, ls=":", label="Capacidad base: 50 / 10.000")
        ax.axvspan(50, 235, color=red, alpha=.05)
        ax.set_xlim(0, 235)
        ax.set_xlabel("Alertas totales por 10.000 operaciones")
        ax.grid(alpha=.15)
    axes[0].legend(loc="lower right", fontsize=8, frameon=False)
    fig.suptitle("2019: los mismos 123 fraudes y el mismo RF · umbrales elegidos en 2018", fontsize=12, weight="bold")
    fig.savefig(figures / "recall_carga_costo_2019.png", dpi=180)
    fig.savefig(figures / "recall_carga_costo_2019.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12.3, 4.4), sharey=True, layout="constrained")
    for ax, year in zip(axes, [2015, 2016, 2019]):
        m = monthly[(monthly.evaluation_year == year) & (monthly.policy == "base_min_cost_capacity")]
        ax.bar(m.month.str[-2:], m.alerts_per_10000, color=blue, alpha=.88)
        ax.axhline(50, color=red, ls="--")
        ax.set_yscale("log")
        ax.set_ylim(5, 5000)
        ax.set_title(str(year))
        ax.set_xlabel("Mes")
        ax.tick_params(axis="x", labelsize=8)
        ax.grid(axis="y", alpha=.15)
        ax.text(.04, .97, f"{int(m.capacity_exceeded.sum())} de {len(m)} meses sobre el límite", transform=ax.transAxes, va="top", fontsize=9)
    axes[0].set_ylabel("Alertas / 10.000 operaciones · escala logarítmica")
    fig.suptitle("La capacidad elegida en validación no garantiza la carga posterior", fontsize=13, weight="bold")
    fig.savefig(figures / "carga_temporal_mensual.png", dpi=180)
    fig.savefig(figures / "carga_temporal_mensual.pdf")
    plt.close(fig)

    # Identify the exact experimental artifact; no model is loaded, changed or promoted.
    prior_models = pd.read_csv(WORK / "finan_ronda2/experimento/modelos_y_tiempos.csv") if (WORK / "finan_ronda2/experimento/modelos_y_tiempos.csv").exists() else pd.read_csv(ROOT / "evidencia_previa/modelos_R2.csv")
    metadata = prior_models[(prior_models.evaluation_year == 2019) & (prior_models.candidate == base.candidate)].iloc[0].to_dict()
    model_file = f"finan_ronda2/experimento/modelo_2019_{base.candidate}.joblib"
    if (WORK / model_file).exists(): assert sha(WORK / model_file) == metadata["model_sha256"]
    write_json(OUT / "propuesta_umbral_2019.json", {"status": "academic_proposal_not_promoted", "model_file_in_R2_package": model_file,
               "model_sha256": metadata["model_sha256"], "threshold": float(base.threshold), "decision_id": base.decision_id,
               "trained_until": metadata["train_end"], "validation": "2018-07-01 <= date < 2019-01-01",
               "review_cost": float(base.review_cost), "fn_cost": float(base.fn_cost), "tp_cost": float(base.review_cost), "tn_cost": 0,
               "capacity_per_10000": 50, "costs_are_assumptions": True, "not_applicable_to_S9_model_without_separate_validation": True})

    write_json(OUT / "verificacion_carga_complementaria.json", {"status": "passed", "monthly_rows": len(extra_monthly),
               "policy_alert_sums_preserved": True, "2019_months_exceeding_capacity": int(e19.capacity_exceeded.sum()),
               "2019_months": len(e19), "2019_peak_per_10000": float(e19.alerts_per_10000.max()),
               "thresholds_unchanged": True})
    print("Tres figuras PNG/PDF y carga mensual complementaria reproducidas.", flush=True)


if __name__ == "__main__":
    run()
