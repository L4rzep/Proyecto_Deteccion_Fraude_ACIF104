"""Selecciona el candidato final comparando los ganadores ML y DL.

Este paso no entrena modelos ni utiliza el conjunto de prueba. Solo consolida
los resultados completos de validacion producidos por los pasos 03 y 04.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    default_results = root / "results" / "models"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=default_results
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def find_row(
    rows: list[dict[str, str]], key: str, value: str, source: str
) -> dict[str, str]:
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        raise ValueError(
            f"{source} no contiene exactamente una fila para {value}"
        )
    return matches[0]


def validate_complete_evidence(
    ml_rows: list[dict[str, str]],
    dl_rows: list[dict[str, str]],
    ml_metadata: dict[str, Any],
    dl_metadata: dict[str, Any],
) -> None:
    expected_ml = {
        "logistic_regression",
        "random_forest",
        "xgboost",
    }
    expected_dl = {
        "mlp_basic_64",
        "mlp_deep_l2_128_64_32",
        "mlp_wide_adam_256_128_64",
    }
    if {row.get("model") for row in ml_rows} != expected_ml:
        raise ValueError("La comparacion ML no contiene los tres modelos")
    if {row.get("architecture") for row in dl_rows} != expected_dl:
        raise ValueError("La comparacion DL no contiene las tres arquitecturas")
    if any(row.get("test_used") != "no" for row in ml_rows + dl_rows):
        raise ValueError("Alguna comparacion declara haber utilizado el test")
    comparable_fields = [
        "seed",
        "sample_modulo",
        "sample_rows",
        "sample_frauds",
        "split",
        "numeric_features",
        "categorical_features",
        "balancing_strategy",
    ]
    mismatches = [
        field
        for field in comparable_fields
        if ml_metadata.get(field) != dl_metadata.get(field)
    ]
    if mismatches:
        raise ValueError(
            "ML y DL no se evaluaron con la misma evidencia: "
            + ", ".join(mismatches)
        )
    if ml_metadata.get("test_policy") is None:
        raise ValueError("Falta la politica de test en la evidencia ML")
    if dl_metadata.get("test_policy") is None:
        raise ValueError("Falta la politica de test en la evidencia DL")


def candidate_row(
    family: str,
    name: str,
    source: dict[str, str],
) -> dict[str, Any]:
    return {
        "family": family,
        "candidate": name,
        "validation_pr_auc": float(source["validation_pr_auc"]),
        "validation_roc_auc": float(source["validation_roc_auc"]),
        "tuned_threshold": float(source["tuned_threshold"]),
        "tuned_precision": float(source["tuned_precision"]),
        "tuned_recall": float(source["tuned_recall"]),
        "tuned_f1": float(source["tuned_f1"]),
        "training_seconds": float(source["training_seconds"]),
        "test_used": "no",
    }


def plot_comparison(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    positions = np.arange(len(rows))
    width = 0.19
    figure, axis = plt.subplots(figsize=(9, 5.5))
    series = [
        ("validation_pr_auc", "PR-AUC"),
        ("tuned_precision", "Precision"),
        ("tuned_recall", "Recall"),
        ("tuned_f1", "F1"),
    ]
    for offset, (key, label) in enumerate(series):
        axis.bar(
            positions + (offset - 1.5) * width,
            [float(row[key]) for row in rows],
            width,
            label=label,
        )
    axis.set_xticks(positions)
    axis.set_xticklabels(
        [f"{row['family']}: {row['candidate']}" for row in rows]
    )
    axis.set_ylim(0, 1)
    axis.set_ylabel("Valor en validacion")
    axis.set_title("Comparacion del ganador ML y el ganador DL")
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    required = {
        "ml_csv": results_dir / "ml_model_comparison.csv",
        "dl_csv": results_dir / "dl_architecture_comparison.csv",
        "ml_selected": results_dir / "ml_model_selected.json",
        "dl_selected": results_dir / "dl_architecture_selected.json",
        "ml_metadata": results_dir / "ml_model_metadata.json",
        "dl_metadata": results_dir / "dl_architecture_metadata.json",
    }
    missing = [path.name for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "No se puede seleccionar el candidato final. Faltan: "
            + ", ".join(missing)
        )

    ml_rows = read_csv(required["ml_csv"])
    dl_rows = read_csv(required["dl_csv"])
    ml_selected = read_json(required["ml_selected"])
    dl_selected = read_json(required["dl_selected"])
    ml_metadata = read_json(required["ml_metadata"])
    dl_metadata = read_json(required["dl_metadata"])
    if ml_selected.get("test_used") is not False:
        raise ValueError("El ganador ML no mantiene reservado el test")
    if dl_selected.get("test_used") is not False:
        raise ValueError("El ganador DL no mantiene reservado el test")
    validate_complete_evidence(
        ml_rows,
        dl_rows,
        ml_metadata,
        dl_metadata,
    )

    ml_name = str(ml_selected["model"])
    dl_name = str(dl_selected["architecture"])
    ml_row = find_row(ml_rows, "model", ml_name, "ML")
    dl_row = find_row(dl_rows, "architecture", dl_name, "DL")
    candidates = [
        candidate_row("ML", ml_name, ml_row),
        candidate_row("DL", dl_name, dl_row),
    ]
    winner = sorted(
        candidates,
        key=lambda row: (
            float(row["validation_pr_auc"]),
            float(row["tuned_f1"]),
            float(row["tuned_recall"]),
        ),
        reverse=True,
    )[0]

    write_csv(results_dir / "final_candidate_comparison.csv", candidates)
    plot_comparison(
        candidates, results_dir / "final_candidate_comparison.png"
    )
    selected = {
        "family": winner["family"],
        "candidate": winner["candidate"],
        "validation_threshold": winner["tuned_threshold"],
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "balancing_strategy": "no_balancing",
        "test_used": False,
        "next_step": "refine_selected_candidate_without_using_test",
    }
    (results_dir / "final_candidate_selected.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "evidence": [path.name for path in required.values()],
        "database": ml_metadata.get("database", "FraudeDB"),
        "seed": ml_metadata["seed"],
        "sample_modulo": ml_metadata["sample_modulo"],
        "sample_rows": ml_metadata["sample_rows"],
        "sample_frauds": ml_metadata["sample_frauds"],
        "split": ml_metadata["split"],
        "numeric_features": ml_metadata["numeric_features"],
        "categorical_features": ml_metadata["categorical_features"],
        "balancing_strategy": ml_metadata["balancing_strategy"],
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "test_policy": (
            "Este paso solo compara resultados de validacion. El test sigue "
            "reservado y no fue cargado ni utilizado."
        ),
    }
    (results_dir / "final_candidate_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Comparacion ML vs. DL completada.")
    for row in candidates:
        print(
            f"- {row['family']} {row['candidate']}: "
            f"PR-AUC={row['validation_pr_auc']:.6f}; "
            f"F1={row['tuned_f1']:.6f}; "
            f"Recall={row['tuned_recall']:.6f}; "
            f"Precision={row['tuned_precision']:.6f}"
        )
    print(
        f"Candidato final para refinamiento: "
        f"{winner['family']} {winner['candidate']}"
    )
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
