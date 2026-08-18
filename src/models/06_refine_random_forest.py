"""Refina Random Forest sin utilizar el conjunto de prueba reservado.

Lee las decisiones de las etapas anteriores, reconstruye la misma muestra
deterministica y la misma division estratificada 70/15/15. Compara tres
configuraciones de Random Forest usando solo entrenamiento y validacion.

El entrenamiento se realiza en bloques de arboles con ``warm_start`` para
mostrar avance real. El conjunto de prueba se separa y cuenta, pero no se
transforma, predice ni utiliza para seleccionar parametros o umbral.
"""

from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any


CONFIGURATIONS: list[dict[str, Any]] = [
    {
        "candidate": "rf_reference_100_d12_leaf2",
        "n_estimators": 100,
        "max_depth": 12,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
    },
    {
        "candidate": "rf_more_trees_200_d12_leaf2",
        "n_estimators": 200,
        "max_depth": 12,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
    },
    {
        "candidate": "rf_deeper_200_d16_leaf2",
        "n_estimators": 200,
        "max_depth": 16,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
    },
]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    results_dir = root / "results" / "models"
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
    parser.add_argument("--tree-block-size", type=int, default=25)
    parser.add_argument(
        "--feature-selection-file",
        type=Path,
        default=results_dir / "feature_configuration_selected.json",
    )
    parser.add_argument(
        "--balancing-selection-file",
        type=Path,
        default=results_dir / "balancing_strategy_selected.json",
    )
    parser.add_argument(
        "--final-candidate-file",
        type=Path,
        default=results_dir / "final_candidate_selected.json",
    )
    parser.add_argument(
        "--final-candidate-metadata-file",
        type=Path,
        default=results_dir / "final_candidate_metadata.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=results_dir,
    )
    return parser.parse_args()


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no valido: {name}")
    return f"[{name}]"


def read_json(path: Path) -> dict[str, Any]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_selections(
    args: argparse.Namespace,
) -> tuple[list[str], list[str], dict[str, Any]]:
    required = [
        args.feature_selection_file,
        args.balancing_selection_file,
        args.final_candidate_file,
        args.final_candidate_metadata_file,
    ]
    missing = [path.name for path in required if not path.resolve().exists()]
    if missing:
        raise FileNotFoundError(
            "Faltan decisiones requeridas: " + ", ".join(missing)
        )

    feature_selection = read_json(args.feature_selection_file)
    numeric = list(feature_selection.get("numeric_features", []))
    categorical = list(feature_selection.get("categorical_features", []))
    if not numeric or not categorical:
        raise ValueError("La configuracion seleccionada no contiene variables")
    if "is_fraud" in numeric + categorical:
        raise ValueError("is_fraud no puede formar parte de las entradas")
    if len(numeric + categorical) != len(set(numeric + categorical)):
        raise ValueError("La configuracion contiene variables duplicadas")
    if feature_selection.get("test_used") is not False:
        raise ValueError("La seleccion de variables no confirma el test reservado")

    balancing_selection = read_json(args.balancing_selection_file)
    if balancing_selection.get("scenario") != "no_balancing":
        raise ValueError(
            "El refinamiento esperaba la estrategia seleccionada no_balancing"
        )
    if balancing_selection.get("test_used") is not False:
        raise ValueError("La seleccion de balanceo no confirma el test reservado")

    final_candidate = read_json(args.final_candidate_file)
    if final_candidate.get("family") != "ML":
        raise ValueError("El candidato final seleccionado no pertenece a ML")
    if final_candidate.get("candidate") != "random_forest":
        raise ValueError("El candidato final seleccionado no es Random Forest")
    if final_candidate.get("test_used") is not False:
        raise ValueError("La seleccion final no confirma el test reservado")

    metadata = read_json(args.final_candidate_metadata_file)
    if metadata.get("seed", args.seed) != args.seed:
        raise ValueError("La semilla no coincide con la seleccion final")
    if metadata.get("sample_modulo", args.sample_modulo) != args.sample_modulo:
        raise ValueError("El modulo de muestra no coincide con la seleccion final")
    if metadata.get("numeric_features") != numeric:
        raise ValueError("Las variables numericas no coinciden con la seleccion final")
    if metadata.get("categorical_features") != categorical:
        raise ValueError(
            "Las variables categoricas no coinciden con la seleccion final"
        )
    if metadata.get("balancing_strategy") != "no_balancing":
        raise ValueError("La estrategia final no coincide con no_balancing")
    return numeric, categorical, metadata


def connect(args: argparse.Namespace) -> Any:
    import pyodbc

    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(
        connection_string,
        autocommit=True,
        timeout=30,
    )


def validate_schema(
    connection: Any,
    numeric: list[str],
    categorical: list[str],
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = 'vw_dataset_maestro'
        """
    )
    actual = {str(row[0]) for row in cursor.fetchall()}
    cursor.close()
    expected = {"transaction_id", "is_fraud", *numeric, *categorical}
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
        blocks.append(pd.DataFrame.from_records(rows, columns=columns))
        loaded += len(rows)
        print(f"Datos leidos: {loaded:,} filas", flush=True)
    cursor.close()
    if not blocks:
        raise RuntimeError("La muestra de modelamiento quedo vacia")
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
        [sparse.csr_matrix(train_numeric), train_categorical],
        format="csr",
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
        "fit_scope": "training_only",
    }
    return train_matrix, validation_matrix, preprocessing


def best_f1_threshold(target: Any, probabilities: Any) -> float:
    import numpy as np
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(
        target,
        probabilities,
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
    target: Any,
    probabilities: Any,
    threshold: float,
    prefix: str,
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
        target,
        predictions,
        labels=[0, 1],
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


def tree_targets(total: int, block_size: int) -> list[int]:
    targets = list(range(block_size, total, block_size))
    targets.append(total)
    return targets


def evaluate_configuration(
    configuration: dict[str, Any],
    train_matrix: Any,
    train_target: Any,
    validation_matrix: Any,
    validation_target: Any,
    args: argparse.Namespace,
    trees_completed_before: int,
    total_trees_all: int,
) -> tuple[dict[str, Any], int]:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score

    total_trees = int(configuration["n_estimators"])
    parameters = {
        "n_estimators": total_trees,
        "max_depth": int(configuration["max_depth"]),
        "min_samples_leaf": int(configuration["min_samples_leaf"]),
        "max_features": str(configuration["max_features"]),
        "bootstrap": True,
        "class_weight": None,
        "random_state": args.seed,
        "n_jobs": -1,
    }
    model = RandomForestClassifier(
        **parameters,
        warm_start=True,
    )
    training_start = perf_counter()
    previous_target = 0
    for target_trees in tree_targets(total_trees, args.tree_block_size):
        model.set_params(n_estimators=target_trees)
        block_start = perf_counter()
        model.fit(train_matrix, train_target)
        block_seconds = perf_counter() - block_start
        trees_added = target_trees - previous_target
        previous_target = target_trees
        trees_done = trees_completed_before + target_trees
        overall = 25.0 + 69.0 * trees_done / total_trees_all
        print(
            f"  [{configuration['candidate']}] arboles "
            f"{target_trees}/{total_trees} "
            f"({target_trees / total_trees:.0%}); "
            f"bloque={trees_added}; tiempo={block_seconds:.1f} s; "
            f"progreso general={overall:.0f} %",
            flush=True,
        )
    training_seconds = perf_counter() - training_start

    prediction_start = perf_counter()
    probabilities = model.predict_proba(validation_matrix)[:, 1]
    prediction_seconds = perf_counter() - prediction_start
    tuned_threshold = best_f1_threshold(validation_target, probabilities)
    result = {
        "candidate": configuration["candidate"],
        "training_rows": int(train_matrix.shape[0]),
        "training_frauds": int(train_target.sum()),
        **parameters,
        "tree_block_size": int(args.tree_block_size),
        "training_seconds": round(float(training_seconds), 4),
        "validation_prediction_seconds": round(float(prediction_seconds), 4),
        "validation_roc_auc": round(
            float(roc_auc_score(validation_target, probabilities)),
            8,
        ),
        "validation_pr_auc": round(
            float(average_precision_score(validation_target, probabilities)),
            8,
        ),
        **threshold_metrics(
            validation_target,
            probabilities,
            0.5,
            "default",
        ),
        **threshold_metrics(
            validation_target,
            probabilities,
            tuned_threshold,
            "tuned",
        ),
        "test_used": "no",
    }
    del model, probabilities
    gc.collect()
    return result, total_trees


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No hay filas para escribir en {path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_results(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    positions = np.arange(len(rows))
    width = 0.19
    figure, axis = plt.subplots(figsize=(11, 6))
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
        [str(row["candidate"]) for row in rows],
        rotation=12,
        ha="right",
    )
    axis.set_ylim(0, 1)
    axis.set_ylabel("Valor en validacion")
    axis.set_title("Refinamiento de Random Forest")
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
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
            "El modulo de muestra y el tamano de bloque deben ser positivos"
        )
    if args.tree_block_size <= 0:
        raise ValueError("tree-block-size debe ser positivo")

    numeric, categorical, reference_metadata = read_selections(args)
    print("Progreso general: 0 % - decisiones verificadas", flush=True)
    connection = connect(args)
    try:
        validate_schema(connection, numeric, categorical)
        data = load_sample(connection, args, numeric, categorical)
    finally:
        connection.close()
    print("Progreso general: 15 % - muestra cargada", flush=True)

    sample_rows = int(len(data))
    target = data["is_fraud"]
    sample_frauds = int(target.sum())
    train_indices, validation_indices, test_indices = split_indices(
        target,
        args.seed,
    )
    split_summary = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    if sample_rows != int(reference_metadata.get("sample_rows", -1)):
        raise ValueError("La cantidad de filas no coincide con la seleccion final")
    if sample_frauds != int(reference_metadata.get("sample_frauds", -1)):
        raise ValueError("La cantidad de fraudes no coincide con la seleccion final")
    if split_summary != reference_metadata.get("split"):
        raise ValueError("La division 70/15/15 no coincide con la seleccion final")

    train_data = data.iloc[train_indices][numeric + categorical]
    validation_data = data.iloc[validation_indices][numeric + categorical]
    train_target = target.iloc[train_indices]
    validation_target = target.iloc[validation_indices]
    del data, target, test_indices
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
        f"{train_matrix.shape[1]:,} columnas.",
        flush=True,
    )
    print("Progreso general: 25 % - datos preparados", flush=True)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = output_dir / "rf_refinement_comparison.csv"
    results: list[dict[str, Any]] = []
    total_trees_all = sum(
        int(configuration["n_estimators"])
        for configuration in CONFIGURATIONS
    )
    completed_trees = 0
    for position, configuration in enumerate(CONFIGURATIONS, start=1):
        print(
            f"Evaluando {position}/{len(CONFIGURATIONS)}: "
            f"{configuration['candidate']}",
            flush=True,
        )
        result, trees_built = evaluate_configuration(
            configuration,
            train_matrix,
            train_target,
            validation_matrix,
            validation_target,
            args,
            completed_trees,
            total_trees_all,
        )
        completed_trees += trees_built
        results.append(result)
        write_csv(comparison_path, results)
        print(
            f"  PR-AUC={result['validation_pr_auc']:.6f}; "
            f"F1={result['tuned_f1']:.6f}; "
            f"Recall={result['tuned_recall']:.6f}; "
            f"Precision={result['tuned_precision']:.6f}; "
            f"entrenamiento={result['training_seconds']:.2f} s",
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
    plot_results(
        results,
        output_dir / "rf_refinement_comparison.png",
    )
    parameters = {
        "n_estimators": int(winner["n_estimators"]),
        "max_depth": int(winner["max_depth"]),
        "min_samples_leaf": int(winner["min_samples_leaf"]),
        "max_features": str(winner["max_features"]),
        "bootstrap": True,
        "class_weight": None,
        "random_state": args.seed,
        "n_jobs": -1,
        "warm_start": False,
    }
    selected = {
        "candidate": winner["candidate"],
        "parameters": parameters,
        "validation_threshold": float(winner["tuned_threshold"]),
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "test_used": False,
    }
    (output_dir / "rf_refinement_selected.json").write_text(
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
        "final_candidate": args.final_candidate_file.name,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "preprocessing": preprocessing,
        "configurations": CONFIGURATIONS,
        "training_protocol": {
            "warm_start": True,
            "tree_block_size": args.tree_block_size,
            "purpose": "progress_reporting_without_changing_final_forest",
        },
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "test_policy": (
            "El conjunto de prueba fue separado y contado, pero no fue "
            "transformado, predicho ni utilizado para refinar Random Forest."
        ),
        "test_used": False,
        "package_versions": package_versions(),
    }
    (output_dir / "rf_refinement_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Progreso general: 100 % - resultados guardados", flush=True)
    print(f"Configuracion seleccionada: {winner['candidate']}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
