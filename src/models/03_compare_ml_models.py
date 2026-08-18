"""Compara tres técnicas de aprendizaje automático con la misma evidencia.

Utiliza la configuración de variables ampliada, la estrategia sin balanceo y
la división estratificada 70/15/15 seleccionadas en las etapas anteriores.
Compara Regresión Logística, Random Forest y XGBoost únicamente con el conjunto
de validación. El conjunto de prueba se separa, pero no se transforma ni usa.
"""

from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import os
from pathlib import Path
from threading import Event, Thread
from time import perf_counter
from typing import Any


MODELS = ["logistic_regression", "random_forest", "xgboost"]
MODEL_LABELS = {
    "logistic_regression": "Regresión logística",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-modulo", type=int, default=9)
    parser.add_argument("--fetch-size", type=int, default=50_000)
    parser.add_argument(
        "--only-model",
        choices=MODELS,
        help=(
            "Recalcula un solo modelo y conserva los otros resultados del "
            "CSV existente."
        ),
    )
    parser.add_argument(
        "--feature-selection-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "feature_configuration_selected.json",
    )
    parser.add_argument(
        "--balancing-selection-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "balancing_strategy_selected.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "models",
    )
    return parser.parse_args()


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no válido: {name}")
    return f"[{name}]"


def read_json(path: Path) -> dict[str, Any]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_selections(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    feature_selection = read_json(args.feature_selection_file)
    numeric = list(feature_selection.get("numeric_features", []))
    categorical = list(feature_selection.get("categorical_features", []))
    if not numeric or not categorical:
        raise ValueError("La configuración seleccionada no contiene variables")
    if "is_fraud" in numeric + categorical:
        raise ValueError("is_fraud no puede formar parte de las entradas")
    if len(numeric + categorical) != len(set(numeric + categorical)):
        raise ValueError("La configuración contiene variables duplicadas")

    balancing_selection = read_json(args.balancing_selection_file)
    if balancing_selection.get("scenario") != "no_balancing":
        raise ValueError(
            "La comparación ML esperaba la estrategia seleccionada "
            "no_balancing"
        )
    if balancing_selection.get("test_used") is not False:
        raise ValueError("La selección de balanceo no confirma el test reservado")
    return numeric, categorical


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


def validate_schema(
    connection: Any, numeric: list[str], categorical: list[str]
) -> None:
    if not connection.execute(
        "SELECT CASE WHEN OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') "
        "IS NULL THEN 0 ELSE 1 END"
    ).fetchval():
        raise RuntimeError("No existe dbo.vw_dataset_maestro")
    actual = {
        str(row[0])
        for row in connection.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'vw_dataset_maestro'"
        ).fetchall()
    }
    expected = {*numeric, *categorical, "transaction_id", "is_fraud"}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "Faltan variables requeridas en la vista: " + ", ".join(missing)
        )


def load_sample(
    connection: Any,
    args: argparse.Namespace,
    numeric: list[str],
    categorical: list[str],
) -> Any:
    import pandas as pd

    features = list(dict.fromkeys(numeric + categorical))
    columns_sql = ", ".join(quote_identifier(name) for name in features)
    safe_seed = int(args.seed)
    safe_modulo = int(args.sample_modulo)
    query = f"""
        SELECT transaction_id, {columns_sql}, is_fraud
        FROM dbo.vw_dataset_maestro
        WHERE (CHECKSUM(transaction_id, {safe_seed}) & 2147483647)
              % {safe_modulo} = 0
        ORDER BY transaction_id
    """
    cursor = connection.cursor()
    cursor.arraysize = args.fetch_size
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    blocks = []
    loaded = 0
    while True:
        rows = cursor.fetchmany(args.fetch_size)
        if not rows:
            break
        block = pd.DataFrame.from_records(rows, columns=columns)
        blocks.append(block)
        loaded += len(block)
        print(f"Datos leídos: {loaded:,} filas")
    cursor.close()
    if not blocks:
        raise RuntimeError("La muestra de modelamiento quedó vacía")
    data = pd.concat(blocks, ignore_index=True)
    del blocks
    data.drop(columns=["transaction_id"], inplace=True)
    for column in numeric:
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


def prepare_matrices(
    train_data: Any,
    validation_data: Any,
    numeric: list[str],
    categorical: list[str],
) -> tuple[Any, Any, dict[str, Any]]:
    import numpy as np
    from scipy import sparse
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    numeric_imputer = SimpleImputer(strategy="median")
    numeric_scaler = StandardScaler()
    train_numeric = numeric_scaler.fit_transform(
        numeric_imputer.fit_transform(train_data[numeric])
    )
    validation_numeric = numeric_scaler.transform(
        numeric_imputer.transform(validation_data[numeric])
    )

    categorical_imputer = SimpleImputer(strategy="most_frequent")
    train_categories = categorical_imputer.fit_transform(
        train_data[categorical]
    )
    validation_categories = categorical_imputer.transform(
        validation_data[categorical]
    )
    ordinal = OrdinalEncoder(
        handle_unknown="use_encoded_value",
        unknown_value=-1,
    )
    train_categories_encoded = ordinal.fit_transform(train_categories)
    validation_categories_encoded = ordinal.transform(validation_categories)
    one_hot = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    train_categorical = one_hot.fit_transform(train_categories_encoded)
    validation_categorical = one_hot.transform(validation_categories_encoded)

    train_matrix = sparse.hstack(
        [sparse.csr_matrix(train_numeric), train_categorical], format="csr"
    )
    validation_matrix = sparse.hstack(
        [sparse.csr_matrix(validation_numeric), validation_categorical],
        format="csr",
    )
    preprocessing = {
        "numeric_imputation": "median",
        "numeric_scaling": "standard",
        "categorical_imputation": "most_frequent",
        "categorical_encoding": "ordinal_then_one_hot",
        "matrix_columns": int(train_matrix.shape[1]),
    }
    return train_matrix, validation_matrix, preprocessing


def build_model(model_name: str, seed: int) -> tuple[Any, dict[str, Any]]:
    if model_name == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        parameters = {
            "solver": "saga",
            "max_iter": 1000,
            "tol": 0.001,
            "C": 1.0,
            "class_weight": None,
            "random_state": seed,
        }
        return LogisticRegression(**parameters), parameters
    if model_name == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        parameters = {
            "n_estimators": 100,
            "max_depth": 12,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
            "bootstrap": True,
            "class_weight": None,
            "random_state": seed,
            "n_jobs": -1,
        }
        return RandomForestClassifier(**parameters), parameters
    if model_name == "xgboost":
        from xgboost import XGBClassifier

        parameters = {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.10,
            "subsample": 0.80,
            "colsample_bytree": 0.80,
            "objective": "binary:logistic",
            "eval_metric": "aucpr",
            "tree_method": "hist",
            "random_state": seed,
            "n_jobs": -1,
            "verbosity": 0,
        }
        return XGBClassifier(**parameters), parameters
    raise ValueError(f"Modelo desconocido: {model_name}")


def best_f1_threshold(target: Any, probabilities: Any) -> float:
    import numpy as np
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(
        target, probabilities
    )
    if thresholds.size == 0:
        return 0.5
    denominator = precision[:-1] + recall[:-1]
    f1_values = np.divide(
        2.0 * precision[:-1] * recall[:-1],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator != 0,
    )
    return float(thresholds[int(np.argmax(f1_values))])


def threshold_metrics(
    target: Any, probabilities: Any, threshold: float, prefix: str
) -> dict[str, Any]:
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    predictions = (probabilities >= threshold).astype("int8")
    precision, recall, f1, _ = precision_recall_fscore_support(
        target,
        predictions,
        average="binary",
        zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(
        target, predictions, labels=[0, 1]
    ).ravel()
    return {
        f"{prefix}_threshold": round(float(threshold), 8),
        f"{prefix}_precision": round(float(precision), 8),
        f"{prefix}_recall": round(float(recall), 8),
        f"{prefix}_f1": round(float(f1), 8),
        f"{prefix}_true_negatives": int(tn),
        f"{prefix}_false_positives": int(fp),
        f"{prefix}_false_negatives": int(fn),
        f"{prefix}_true_positives": int(tp),
    }


def training_heartbeat(
    model_name: str, stop_event: Event, interval_seconds: int = 20
) -> None:
    """Avisa periódicamente que el entrenamiento continúa activo."""
    start = perf_counter()
    while not stop_event.wait(interval_seconds):
        elapsed = int(perf_counter() - start)
        print(
            f"  [{MODEL_LABELS[model_name]}] sigue entrenando; "
            f"tiempo transcurrido: {elapsed} s.",
            flush=True,
        )


def evaluate_model(
    model_name: str,
    train_matrix: Any,
    train_target: Any,
    validation_matrix: Any,
    validation_target: Any,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from sklearn.metrics import average_precision_score, roc_auc_score

    model, parameters = build_model(model_name, seed)
    print(f"  [{MODEL_LABELS[model_name]}] avance: 0 %", flush=True)
    stop_event = Event()
    heartbeat = Thread(
        target=training_heartbeat,
        args=(model_name, stop_event),
        daemon=True,
    )
    heartbeat.start()
    training_start = perf_counter()
    try:
        model.fit(train_matrix, train_target)
        training_seconds = perf_counter() - training_start
    finally:
        stop_event.set()
        heartbeat.join(timeout=1)
    print(f"  [{MODEL_LABELS[model_name]}] avance: 100 %", flush=True)
    prediction_start = perf_counter()
    probabilities = model.predict_proba(validation_matrix)[:, 1]
    prediction_seconds = perf_counter() - prediction_start
    tuned_threshold = best_f1_threshold(validation_target, probabilities)
    if model_name == "logistic_regression":
        training_iterations: int | str = int(model.n_iter_[0])
        convergence_reached = (
            "yes" if training_iterations < parameters["max_iter"] else "no"
        )
    else:
        training_iterations = ""
        convergence_reached = "not_applicable"
    result = {
        "model": model_name,
        "training_rows": int(train_matrix.shape[0]),
        "training_frauds": int(train_target.sum()),
        "training_seconds": round(float(training_seconds), 4),
        "training_iterations": training_iterations,
        "convergence_reached": convergence_reached,
        "validation_prediction_seconds": round(float(prediction_seconds), 4),
        "validation_roc_auc": round(
            float(roc_auc_score(validation_target, probabilities)), 8
        ),
        "validation_pr_auc": round(
            float(average_precision_score(validation_target, probabilities)),
            8,
        ),
        **threshold_metrics(
            validation_target, probabilities, 0.5, "default"
        ),
        **threshold_metrics(
            validation_target, probabilities, tuned_threshold, "tuned"
        ),
        "test_used": "no",
    }
    del model, probabilities
    gc.collect()
    return result, parameters


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_previous_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            "No existe la comparación anterior necesaria para recalcular "
            "un solo modelo"
        )
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if {row.get("model") for row in rows} != set(MODELS):
        raise ValueError("La comparación anterior no contiene los tres modelos")
    for row in rows:
        row.setdefault("training_iterations", "")
        row.setdefault("convergence_reached", "not_recorded")
    return rows


def plot_results(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    positions = np.arange(len(rows))
    width = 0.19
    figure, axis = plt.subplots(figsize=(12, 6.5))
    series = [
        ("validation_pr_auc", "PR-AUC"),
        ("tuned_precision", "Precisión"),
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
    axis.set_xticklabels([MODEL_LABELS[row["model"]] for row in rows])
    axis.set_ylim(0, 1)
    axis.set_ylabel("Valor en validación")
    axis.set_title("Comparación de técnicas de aprendizaje automático")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def package_versions() -> dict[str, str]:
    packages = [
        "numpy",
        "pandas",
        "pyodbc",
        "scipy",
        "scikit-learn",
        "xgboost",
        "matplotlib",
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def main() -> int:
    args = parse_args()
    if args.sample_modulo <= 0 or args.fetch_size <= 0:
        raise ValueError(
            "El módulo de muestra y el tamaño de bloque deben ser positivos"
        )

    print("Progreso general: 0 % - inicio", flush=True)
    numeric, categorical = read_selections(args)
    connection = connect(args)
    try:
        validate_schema(connection, numeric, categorical)
        data = load_sample(connection, args, numeric, categorical)
    finally:
        connection.close()
    print("Progreso general: 20 % - muestra cargada", flush=True)

    sample_rows = int(len(data))
    target = data["is_fraud"]
    sample_frauds = int(target.sum())
    train_indices, validation_indices, test_indices = split_indices(
        target, args.seed
    )
    split_summary = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    train_data = data.iloc[train_indices][numeric + categorical]
    validation_data = data.iloc[validation_indices][numeric + categorical]
    train_target = target.iloc[train_indices]
    validation_target = target.iloc[validation_indices]
    del data
    train_matrix, validation_matrix, preprocessing = prepare_matrices(
        train_data,
        validation_data,
        numeric,
        categorical,
    )
    del train_data, validation_data
    gc.collect()
    print(
        "Matriz preparada: "
        f"{train_matrix.shape[0]:,} filas y "
        f"{train_matrix.shape[1]:,} columnas."
    )
    print("Progreso general: 30 % - datos preparados", flush=True)

    results = []
    model_parameters = {}
    overall_progress = {
        "logistic_regression": 52,
        "random_forest": 74,
        "xgboost": 96,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    models_to_run = [args.only_model] if args.only_model else MODELS
    if args.only_model:
        results = read_previous_results(
            output_dir / "ml_model_comparison.csv"
        )
        previous_metadata = read_json(output_dir / "ml_model_metadata.json")
        model_parameters = dict(previous_metadata.get("model_parameters", {}))
        print(
            f"Se recalculará únicamente {MODEL_LABELS[args.only_model]}; "
            "los otros resultados se conservarán."
        )
    for position, model_name in enumerate(models_to_run, start=1):
        print(
            f"Evaluando {position}/{len(models_to_run)}: {model_name}"
        )
        result, parameters = evaluate_model(
            model_name,
            train_matrix,
            train_target,
            validation_matrix,
            validation_target,
            args.seed,
        )
        results = [row for row in results if row.get("model") != model_name]
        results.append(result)
        results.sort(key=lambda row: MODELS.index(str(row["model"])))
        model_parameters[model_name] = parameters
        print(
            f"  PR-AUC={result['validation_pr_auc']:.6f}; "
            f"F1={result['tuned_f1']:.6f}; "
            f"Recall={result['tuned_recall']:.6f}; "
            f"Precisión={result['tuned_precision']:.6f}; "
            f"entrenamiento={result['training_seconds']:.2f} s"
        )
        completed_progress = (
            96 if args.only_model else overall_progress[model_name]
        )
        print(
            f"Progreso general: {completed_progress} % - "
            f"{MODEL_LABELS[model_name]} terminado",
            flush=True,
        )

    winner = sorted(
        results,
        key=lambda row: (
            float(row["validation_pr_auc"]),
            float(row["tuned_f1"]),
            float(row["tuned_recall"]),
        ),
        reverse=True,
    )[0]
    write_csv(output_dir / "ml_model_comparison.csv", results)
    plot_results(results, output_dir / "ml_model_comparison.png")
    selected = {
        "model": winner["model"],
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "validation_threshold": float(winner["tuned_threshold"]),
        "balancing_strategy": "no_balancing",
        "test_used": False,
        "note": (
            "El modelo y el umbral deben confirmarse después de la comparación "
            "con Deep Learning y antes de evaluar una sola vez el test final."
        ),
    }
    (output_dir / "ml_model_selected.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "database": args.database,
        "seed": args.seed,
        "sample_modulo": args.sample_modulo,
        "sample_rows": sample_rows,
        "sample_frauds": sample_frauds,
        "split": split_summary,
        "feature_configuration": args.feature_selection_file.name,
        "balancing_configuration": args.balancing_selection_file.name,
        "balancing_strategy": "no_balancing",
        "numeric_features": numeric,
        "categorical_features": categorical,
        "preprocessing": preprocessing,
        "models": MODELS,
        "model_parameters": model_parameters,
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "test_policy": (
            "El conjunto de prueba fue separado y contado, pero no fue "
            "transformado, predicho ni utilizado para seleccionar el modelo ML."
        ),
        "package_versions": package_versions(),
    }
    (output_dir / "ml_model_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Progreso general: 100 % - resultados guardados", flush=True)
    print(f"Modelo ML seleccionado: {winner['model']}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
