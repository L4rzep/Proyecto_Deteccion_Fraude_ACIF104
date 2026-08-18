"""Evalúa una sola vez el pipeline final sobre el test reservado.

Este paso es deliberadamente irreversible dentro del flujo experimental: exige
una confirmación explícita, reconstruye la misma muestra y división 70/15/15,
no ajusta el modelo ni el umbral y se niega a reemplazar cualquier evidencia
final existente.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


OUTPUT_NAMES = (
    "final_test_metrics.json",
    "final_test_metrics.csv",
    "final_confusion_matrix.png",
    "final_pr_curve.png",
    "final_test_evaluation_metadata.json",
    "final_test_evaluation.lock",
)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-final-test",
        action="store_true",
        help="Confirma el único uso autorizado del conjunto de prueba final.",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("FINAN_SQL_SERVER", r"(localdb)\MSSQLLocalDB"),
    )
    parser.add_argument(
        "--database", default=os.getenv("FINAN_SQL_DATABASE", "FraudeDB")
    )
    parser.add_argument(
        "--driver",
        default=os.getenv("FINAN_SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
    )
    parser.add_argument("--fetch-size", type=int, default=50_000)
    parser.add_argument(
        "--pipeline-file",
        type=Path,
        default=root / "models" / "finan_fraud_pipeline.joblib",
    )
    parser.add_argument(
        "--schema-file",
        type=Path,
        default=root / "models" / "finan_feature_schema.json",
    )
    parser.add_argument(
        "--training-metadata-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "final_model_training_metadata.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "models",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"No existe el archivo requerido: {resolved}")
    with resolved.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un objeto JSON en {resolved}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.resolve().open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_output_absence(output_dir: Path) -> dict[str, Path]:
    paths = {name: output_dir / name for name in OUTPUT_NAMES}
    existing = [str(path.resolve()) for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(
            "La evaluación final ya tiene evidencia y no puede repetirse ni "
            "sobrescribirse:\n- " + "\n- ".join(existing)
        )
    return paths


def schema_hash(schema: dict[str, Any]) -> str:
    candidates = (
        schema.get("model_sha256"),
        schema.get("pipeline_sha256"),
        schema.get("artifact_sha256"),
        schema.get("sha256"),
    )
    nested = schema.get("pipeline")
    if isinstance(nested, dict):
        candidates += (nested.get("sha256"),)
    value = next((item for item in candidates if item), None)
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("El esquema no contiene el SHA-256 válido del pipeline")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("El SHA-256 registrado no es hexadecimal") from exc
    return value.lower()


def read_contract(
    schema: dict[str, Any], metadata: dict[str, Any], pipeline_file: Path
) -> tuple[list[str], list[str], list[str], float, int, int, str]:
    if schema.get("test_used") is not False:
        raise ValueError("El esquema no confirma que el test siguió reservado")
    ordered = schema.get("ordered_features")
    if not isinstance(ordered, list) or not ordered:
        raise ValueError("El esquema no contiene ordered_features")
    if not all(isinstance(item, str) and item for item in ordered):
        raise ValueError("ordered_features contiene nombres no válidos")
    if len(ordered) != len(set(ordered)):
        raise ValueError("ordered_features contiene variables duplicadas")
    if "is_fraud" in ordered or "transaction_id" in ordered:
        raise ValueError("La etiqueta o el identificador aparecen como entrada")

    threshold_value = schema.get("threshold")
    if threshold_value is None:
        threshold_value = schema.get("validation_threshold")
    threshold = float(threshold_value)
    if not 0.0 < threshold < 1.0:
        raise ValueError("El umbral final debe estar entre 0 y 1")

    expected_hash = schema_hash(schema)
    actual_hash = sha256_file(pipeline_file)
    if actual_hash != expected_hash:
        raise ValueError(
            "El hash del pipeline no coincide con finan_feature_schema.json"
        )

    if metadata.get("test_used") is not False:
        raise ValueError(
            "El entrenamiento final no confirma que el test siguió reservado"
        )
    seed = metadata.get("seed")
    sample_modulo = metadata.get("sample_modulo")
    if seed is None or sample_modulo is None:
        sample = metadata.get("sample")
        if isinstance(sample, dict):
            seed = sample.get("seed", seed)
            sample_modulo = sample.get("modulo", sample_modulo)
    if seed is None or sample_modulo is None:
        raise ValueError("Faltan seed o sample_modulo en los metadatos")
    seed = int(seed)
    sample_modulo = int(sample_modulo)
    if sample_modulo <= 1:
        raise ValueError("sample_modulo debe ser mayor que 1")

    numeric = metadata.get("numeric_features", schema.get("numeric_features"))
    categorical = metadata.get(
        "categorical_features", schema.get("categorical_features")
    )
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise ValueError("Faltan las listas de variables numéricas/categóricas")
    if list(numeric) + list(categorical) != ordered:
        raise ValueError(
            "El orden de variables del entrenamiento no coincide con el esquema"
        )

    metadata_hash = metadata.get(
        "model_sha256", metadata.get("pipeline_sha256")
    )
    if metadata_hash is not None and str(metadata_hash).lower() != actual_hash:
        raise ValueError("El hash del pipeline no coincide con los metadatos")
    if metadata.get("pipeline_steps") != ["preprocessor", "model"]:
        raise ValueError("Los metadatos no confirman los steps preprocessor/model")
    recorded_pipeline = metadata.get("pipeline_file")
    if recorded_pipeline and Path(str(recorded_pipeline)).name != pipeline_file.name:
        raise ValueError("El nombre del pipeline no coincide con los metadatos")
    return (
        list(ordered),
        list(numeric),
        list(categorical),
        threshold,
        seed,
        sample_modulo,
        actual_hash,
    )


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no válido: {name}")
    return f"[{name}]"


def connect(args: argparse.Namespace) -> Any:
    import pyodbc

    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(
        connection_string, autocommit=True, timeout=30
    )
    connection.timeout = 0
    return connection


def validate_schema(connection: Any, ordered_features: list[str]) -> None:
    exists = connection.execute(
        "SELECT CASE WHEN OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') "
        "IS NULL THEN 0 ELSE 1 END"
    ).fetchval()
    if not exists:
        raise RuntimeError("No existe dbo.vw_dataset_maestro")
    actual = {
        str(row[0])
        for row in connection.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'vw_dataset_maestro'"
        ).fetchall()
    }
    expected = {*ordered_features, "transaction_id", "is_fraud"}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "Faltan variables requeridas en la vista: " + ", ".join(missing)
        )


def load_same_sample(
    connection: Any,
    ordered_features: list[str],
    numeric_features: list[str],
    seed: int,
    sample_modulo: int,
    fetch_size: int,
) -> Any:
    import pandas as pd

    columns_sql = ", ".join(
        quote_identifier(name) for name in ordered_features
    )
    query = f"""
        SELECT transaction_id, {columns_sql}, is_fraud
        FROM dbo.vw_dataset_maestro
        WHERE (CHECKSUM(transaction_id, {seed}) & 2147483647)
              % {sample_modulo} = 0
        ORDER BY transaction_id
    """
    cursor = connection.cursor()
    cursor.arraysize = fetch_size
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    blocks = []
    loaded = 0
    while True:
        rows = cursor.fetchmany(fetch_size)
        if not rows:
            break
        blocks.append(pd.DataFrame.from_records(rows, columns=columns))
        loaded += len(rows)
        print(f"Reconstruyendo muestra: {loaded:,} filas", flush=True)
    cursor.close()
    if not blocks:
        raise RuntimeError("La muestra de modelamiento quedó vacía")
    data = pd.concat(blocks, ignore_index=True)
    for column in numeric_features:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["is_fraud"] = data["is_fraud"].astype("int8")
    return data


def split_indices(target: Any, seed: int) -> tuple[Any, Any, Any]:
    import numpy as np
    from sklearn.model_selection import train_test_split

    all_indices = np.arange(len(target))
    train_indices, temporary_indices = train_test_split(
        all_indices,
        test_size=0.30,
        random_state=seed,
        stratify=target,
    )
    validation_indices, test_indices = train_test_split(
        temporary_indices,
        test_size=0.50,
        random_state=seed,
        stratify=target.iloc[temporary_indices],
    )
    return train_indices, validation_indices, test_indices


def class_counts(target: Any, indices: Any) -> dict[str, int]:
    subset = target.iloc[indices]
    return {
        "rows": int(len(subset)),
        "frauds": int(subset.sum()),
        "non_frauds": int((subset == 0).sum()),
    }


def validate_reconstructed_split(
    metadata: dict[str, Any], target: Any, split: dict[str, dict[str, int]]
) -> None:
    expected_rows = metadata.get("sample_rows")
    expected_split = metadata.get("split")
    if expected_rows is None:
        raise ValueError("Falta sample_rows en los metadatos")
    if int(expected_rows) != len(target):
        raise RuntimeError(
            "La muestra reconstruida no coincide con el entrenamiento final"
        )
    if not isinstance(expected_split, dict):
        raise ValueError("Falta el resumen split en los metadatos")
    for name, counts in split.items():
        expected = expected_split.get(name)
        if not isinstance(expected, dict):
            raise ValueError(f"Falta split.{name} en los metadatos")
        normalized = {
            key: int(expected.get(key, -1)) for key in counts
        }
        if normalized != counts:
            raise RuntimeError(
                f"La división reconstruida no coincide en {name}: "
                f"esperado={normalized}, actual={counts}"
            )
    expected_frauds = sum(
        int(expected_split[name].get("frauds", -1)) for name in split
    )
    if expected_frauds != int(target.sum()):
        raise RuntimeError(
            "La cantidad de fraudes no coincide con los metadatos de entrenamiento"
        )


def load_pipeline(path: Path) -> Any:
    import joblib

    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"No existe el pipeline final: {resolved}")
    pipeline = joblib.load(resolved)
    steps = getattr(pipeline, "named_steps", None)
    if steps is None or list(steps) != ["preprocessor", "model"]:
        raise ValueError(
            "El artefacto debe ser un Pipeline con steps preprocessor/model"
        )
    if not callable(getattr(pipeline, "predict_proba", None)):
        raise ValueError("El pipeline final no implementa predict_proba")
    classes = list(getattr(pipeline, "classes_", []))
    if classes != [0, 1]:
        raise ValueError(
            "El pipeline debe exponer las clases [0, 1] en ese orden"
        )
    return pipeline


def calculate_metrics(
    target: Any, probabilities: Any, threshold: float
) -> tuple[dict[str, Any], Any]:
    import numpy as np
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        balanced_accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
        roc_auc_score,
    )

    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 1 or len(probabilities) != len(target):
        raise RuntimeError("El pipeline devolvió probabilidades incompatibles")
    if not np.isfinite(probabilities).all():
        raise RuntimeError("El pipeline devolvió probabilidades no finitas")
    predictions = (probabilities >= threshold).astype("int8")
    precision, recall, f1, _ = precision_recall_fscore_support(
        target, predictions, average="binary", zero_division=0
    )
    matrix = confusion_matrix(target, predictions, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    metrics = {
        "threshold": round(float(threshold), 8),
        "test_rows": int(len(target)),
        "test_frauds": int(target.sum()),
        "test_non_frauds": int((target == 0).sum()),
        "precision": round(float(precision), 8),
        "recall": round(float(recall), 8),
        "f1": round(float(f1), 8),
        "specificity": round(float(specificity), 8),
        "accuracy": round(float(accuracy_score(target, predictions)), 8),
        "balanced_accuracy": round(
            float(balanced_accuracy_score(target, predictions)), 8
        ),
        "pr_auc": round(float(average_precision_score(target, probabilities)), 8),
        "roc_auc": round(float(roc_auc_score(target, probabilities)), 8),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
    }
    return metrics, probabilities


def save_confusion_matrix(path: Path, metrics: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    matrix = np.array(
        [
            [metrics["true_negatives"], metrics["false_positives"]],
            [metrics["false_negatives"], metrics["true_positives"]],
        ]
    )
    figure, axis = plt.subplots(figsize=(6.5, 5.5))
    image = axis.imshow(matrix, cmap="Blues")
    figure.colorbar(image, ax=axis)
    axis.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["Legítima", "Fraude"],
        yticklabels=["Legítima", "Fraude"],
        xlabel="Predicción",
        ylabel="Valor real",
        title="Matriz de confusión - test final",
    )
    for row in range(2):
        for column in range(2):
            axis.text(
                column,
                row,
                f"{matrix[row, column]:,}",
                ha="center",
                va="center",
                color="white" if matrix[row, column] > matrix.max() / 2 else "black",
            )
    figure.tight_layout()
    with path.open("xb") as stream:
        figure.savefig(stream, format="png", dpi=160, bbox_inches="tight")
    plt.close(figure)


def save_pr_curve(path: Path, target: Any, probabilities: Any) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import average_precision_score, precision_recall_curve

    precision, recall, _ = precision_recall_curve(target, probabilities)
    pr_auc = average_precision_score(target, probabilities)
    baseline = float(target.mean())
    figure, axis = plt.subplots(figsize=(7, 5.5))
    axis.plot(recall, precision, label=f"Pipeline final (PR-AUC={pr_auc:.4f})")
    axis.axhline(
        baseline,
        linestyle="--",
        color="gray",
        label=f"Prevalencia ({baseline:.4%})",
    )
    axis.set(
        xlabel="Recall",
        ylabel="Precisión",
        title="Curva precisión-recall - test final",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    axis.grid(alpha=0.25)
    axis.legend(loc="best")
    figure.tight_layout()
    with path.open("xb") as stream:
        figure.savefig(stream, format="png", dpi=160, bbox_inches="tight")
    plt.close(figure)


def write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_metrics_csv(path: Path, metrics: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(metrics))
        writer.writeheader()
        writer.writerow(metrics)


def package_versions() -> dict[str, str]:
    versions = {}
    for package in ("joblib", "numpy", "pandas", "pyodbc", "scikit-learn"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def main() -> int:
    args = parse_args()
    if not args.confirm_final_test:
        raise SystemExit(
            "OPERACIÓN CANCELADA: el test final solo puede usarse una vez. "
            "Revise el pipeline, esquema, umbral y metadatos; luego repita "
            "agregando --confirm-final-test."
        )
    if args.fetch_size <= 0:
        raise ValueError("fetch-size debe ser mayor que cero")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = require_output_absence(output_dir)
    schema = read_json(args.schema_file)
    training_metadata = read_json(args.training_metadata_file)
    pipeline_path = args.pipeline_file.resolve()
    (
        ordered_features,
        numeric_features,
        _categorical_features,
        threshold,
        seed,
        sample_modulo,
        pipeline_hash,
    ) = read_contract(schema, training_metadata, pipeline_path)
    pipeline = load_pipeline(pipeline_path)

    print(
        "Confirmación recibida. Se reconstruirá el test reservado y no se "
        "ajustará ningún parámetro.",
        flush=True,
    )
    connection = connect(args)
    try:
        validate_schema(connection, ordered_features)
        data = load_same_sample(
            connection,
            ordered_features,
            numeric_features,
            seed,
            sample_modulo,
            args.fetch_size,
        )
    finally:
        connection.close()

    target = data["is_fraud"]
    train_indices, validation_indices, test_indices = split_indices(target, seed)
    split = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    validate_reconstructed_split(training_metadata, target, split)

    test_data = data.iloc[test_indices][ordered_features].copy()
    test_target = target.iloc[test_indices].copy()
    del data, target, train_indices, validation_indices, test_indices

    started = perf_counter()
    probabilities = pipeline.predict_proba(test_data)[:, 1]
    prediction_seconds = perf_counter() - started
    metrics, probabilities = calculate_metrics(
        test_target, probabilities, threshold
    )
    metrics["prediction_seconds"] = round(float(prediction_seconds), 6)

    evaluation_time = datetime.now(timezone.utc).isoformat()
    evaluation_metadata = {
        "evaluated_at_utc": evaluation_time,
        "evaluation_scope": "reserved_test_only",
        "confirmation_flag": "--confirm-final-test",
        "pipeline_file": str(pipeline_path),
        "pipeline_sha256": pipeline_hash,
        "schema_file": str(args.schema_file.resolve()),
        "schema_sha256": sha256_file(args.schema_file),
        "training_metadata_file": str(args.training_metadata_file.resolve()),
        "training_metadata_sha256": sha256_file(args.training_metadata_file),
        "seed": seed,
        "sample_modulo": sample_modulo,
        "ordered_features": ordered_features,
        "threshold_source": "finan_feature_schema.json",
        "threshold_adjusted_on_test": False,
        "model_refit_on_test": False,
        "split": split,
        "metrics_file": "final_test_metrics.json",
        "software_versions": package_versions(),
    }

    write_json_exclusive(output_paths["final_test_metrics.json"], metrics)
    write_metrics_csv(output_paths["final_test_metrics.csv"], metrics)
    save_confusion_matrix(
        output_paths["final_confusion_matrix.png"], metrics
    )
    save_pr_curve(
        output_paths["final_pr_curve.png"], test_target, probabilities
    )
    write_json_exclusive(
        output_paths["final_test_evaluation_metadata.json"],
        evaluation_metadata,
    )
    write_json_exclusive(
        output_paths["final_test_evaluation.lock"],
        {
            "status": "completed",
            "evaluated_at_utc": evaluation_time,
            "pipeline_sha256": pipeline_hash,
            "metrics_sha256": sha256_file(
                output_paths["final_test_metrics.json"]
            ),
            "warning": (
                "La evaluación final ya fue realizada. No ejecutar nuevamente "
                "ni utilizar el test para ajustar decisiones."
            ),
        },
    )
    print("Evaluación única del test final completada.", flush=True)
    print(f"Resultados guardados en: {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
