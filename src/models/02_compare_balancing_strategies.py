"""Compara sin balanceo, submuestreo y SMOTE sobre la misma partición.

Utiliza la configuración de variables seleccionada en la etapa anterior. Los
tres escenarios comparten la muestra, la división 70/15/15, el preprocesamiento
y los parámetros de XGBoost. La selección se realiza exclusivamente con
validación; el conjunto de prueba permanece reservado.
"""

from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any


SCENARIOS = ["no_balancing", "random_undersampling", "smote"]


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
        "--selection-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "feature_configuration_selected.json",
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


def read_selected_features(path: Path) -> tuple[list[str], list[str]]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        selected = json.load(stream)
    numeric = list(selected.get("numeric_features", []))
    categorical = list(selected.get("categorical_features", []))
    if not numeric or not categorical:
        raise ValueError("La configuración seleccionada no contiene variables")
    if "is_fraud" in numeric + categorical:
        raise ValueError("is_fraud no puede formar parte de las entradas")
    if len(numeric + categorical) != len(set(numeric + categorical)):
        raise ValueError("La configuración contiene variables duplicadas")
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


def prepare_for_sampling(
    train_data: Any,
    validation_data: Any,
    numeric: list[str],
    categorical: list[str],
) -> tuple[Any, Any, Any, int]:
    import numpy as np
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

    pre_sampling_train = np.hstack(
        [train_numeric, train_categories_encoded]
    )
    pre_sampling_validation = np.hstack(
        [validation_numeric, validation_categories_encoded]
    )
    one_hot = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    one_hot.fit(train_categories_encoded)
    return (
        pre_sampling_train,
        pre_sampling_validation,
        one_hot,
        train_numeric.shape[1],
    )


def final_matrix(values: Any, one_hot: Any, numeric_count: int) -> Any:
    from scipy import sparse

    numeric = sparse.csr_matrix(values[:, :numeric_count])
    categorical = one_hot.transform(values[:, numeric_count:])
    return sparse.hstack([numeric, categorical], format="csr")


def resample(
    scenario: str,
    values: Any,
    target: Any,
    numeric_count: int,
    seed: int,
) -> tuple[Any, Any]:
    from imblearn.over_sampling import SMOTENC
    from imblearn.under_sampling import RandomUnderSampler

    if scenario == "no_balancing":
        return values, target
    if scenario == "random_undersampling":
        sampler = RandomUnderSampler(random_state=seed)
        return sampler.fit_resample(values, target)
    if scenario == "smote":
        # SMOTENC 0.14.2 compara este parámetro con el texto "auto".
        # Una lista evita la comparación ambigua que ocurre con un arreglo NumPy.
        categorical_indices = list(range(numeric_count, values.shape[1]))
        sampler = SMOTENC(
            categorical_features=categorical_indices,
            random_state=seed,
            k_neighbors=5,
        )
        return sampler.fit_resample(values, target)
    raise ValueError(f"Escenario desconocido: {scenario}")


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


def evaluate_scenario(
    scenario: str,
    pre_sampling_train: Any,
    train_target: Any,
    validation_matrix: Any,
    validation_target: Any,
    one_hot: Any,
    numeric_count: int,
    seed: int,
) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, roc_auc_score
    from xgboost import XGBClassifier

    sampled_values, sampled_target = resample(
        scenario,
        pre_sampling_train,
        train_target,
        numeric_count,
        seed,
    )
    training_matrix = final_matrix(sampled_values, one_hot, numeric_count)
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.10,
        subsample=0.80,
        colsample_bytree=0.80,
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        random_state=seed,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(training_matrix, sampled_target)
    probabilities = model.predict_proba(validation_matrix)[:, 1]
    tuned_threshold = best_f1_threshold(validation_target, probabilities)
    result = {
        "scenario": scenario,
        "training_rows_before": int(len(train_target)),
        "training_frauds_before": int(train_target.sum()),
        "training_rows_after": int(len(sampled_target)),
        "training_frauds_after": int(sampled_target.sum()),
        "validation_roc_auc": round(
            float(roc_auc_score(validation_target, probabilities)), 8
        ),
        "validation_pr_auc": round(
            float(average_precision_score(validation_target, probabilities)), 8
        ),
        **threshold_metrics(validation_target, probabilities, 0.5, "default"),
        **threshold_metrics(
            validation_target, probabilities, tuned_threshold, "tuned"
        ),
        "test_used": "no",
    }
    del sampled_values, sampled_target, training_matrix, model, probabilities
    gc.collect()
    return result


def plot_results(rows: list[dict[str, Any]], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [
        {
            "no_balancing": "Sin balanceo",
            "random_undersampling": "Submuestreo",
            "smote": "SMOTE",
        }[row["scenario"]]
        for row in rows
    ]
    metrics = [
        ("validation_pr_auc", "PR-AUC"),
        ("tuned_precision", "Precisión"),
        ("tuned_recall", "Recall"),
        ("tuned_f1", "F1"),
    ]
    positions = np.arange(len(labels))
    width = 0.19
    fig, axis = plt.subplots(figsize=(10, 5.5))
    for index, (field, label) in enumerate(metrics):
        values = [float(row[field]) for row in rows]
        axis.bar(
            positions + (index - 1.5) * width,
            values,
            width,
            label=label,
        )
    axis.set_xticks(positions, labels)
    axis.set_ylim(0, 1)
    axis.set_ylabel("Valor en validación")
    axis.set_title("Comparación de estrategias de balanceo")
    axis.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def package_versions() -> dict[str, str]:
    packages = [
        "numpy",
        "pandas",
        "pyodbc",
        "scipy",
        "scikit-learn",
        "imbalanced-learn",
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
        raise ValueError("El módulo de muestra y el tamaño de bloque deben ser positivos")

    numeric, categorical = read_selected_features(args.selection_file)
    connection = connect(args)
    try:
        validate_schema(connection, numeric, categorical)
        data = load_sample(connection, args, numeric, categorical)
    finally:
        connection.close()

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
    pre_train, pre_validation, one_hot, numeric_count = prepare_for_sampling(
        train_data,
        validation_data,
        numeric,
        categorical,
    )
    validation_matrix = final_matrix(
        pre_validation, one_hot, numeric_count
    )
    del train_data, validation_data, pre_validation
    gc.collect()

    results = []
    for position, scenario in enumerate(SCENARIOS, start=1):
        print(f"Evaluando {position}/3: {scenario}")
        result = evaluate_scenario(
            scenario,
            pre_train,
            train_target,
            validation_matrix,
            validation_target,
            one_hot,
            numeric_count,
            args.seed,
        )
        results.append(result)
        print(
            f"  PR-AUC={result['validation_pr_auc']:.6f}; "
            f"F1={result['tuned_f1']:.6f}; "
            f"Recall={result['tuned_recall']:.6f}; "
            f"Precisión={result['tuned_precision']:.6f}"
        )

    ordered = sorted(
        results,
        key=lambda row: (
            row["validation_pr_auc"],
            row["tuned_f1"],
            row["tuned_recall"],
        ),
        reverse=True,
    )
    winner = ordered[0]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "balancing_strategy_comparison.csv", results)
    plot_results(results, output_dir / "balancing_strategy_comparison.png")
    selected = {
        "scenario": winner["scenario"],
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "validation_threshold": winner["tuned_threshold"],
        "test_used": False,
        "note": (
            "El umbral y el escenario todavía deben confirmarse al comparar "
            "todos los modelos antes de evaluar el test final."
        ),
    }
    (output_dir / "balancing_strategy_selected.json").write_text(
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
        "feature_configuration": args.selection_file.name,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "scenarios": SCENARIOS,
        "smote_method": (
            "SMOTENC sobre variables numéricas escaladas y categorías "
            "codificadas; one-hot se aplica después del remuestreo."
        ),
        "test_policy": (
            "El conjunto de prueba fue separado y contado, pero no fue "
            "transformado, predicho ni utilizado para seleccionar balanceo."
        ),
        "package_versions": package_versions(),
    }
    (output_dir / "balancing_strategy_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Estrategia seleccionada: {winner['scenario']}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
