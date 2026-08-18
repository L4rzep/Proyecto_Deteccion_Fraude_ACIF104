"""Compara cuatro configuraciones de variables sin utilizar el test final.

La extracción desde FraudeDB se realiza una sola vez. Después se crea una
división estratificada 70/15/15 y se comparan dos conjuntos de variables con
dos tratamientos del monto. El 15 % de prueba queda reservado y no se usa para
ajustar, predecir ni escoger la configuración ganadora.

Este es un experimento de selección de variables. El modelo XGBoost utilizado
es común a las cuatro configuraciones y no corresponde todavía a la comparación
final de modelos ni a los tres escenarios oficiales de balanceo.
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any


BASE_NUMERIC = [
    "amount",
    "age_at_transaction",
    "num_credit_cards",
    "num_cards_issued",
    "card_account_age_years",
    "months_to_card_expiration",
    "years_since_pin_change",
]

BASE_CATEGORICAL = [
    "transaction_hour",
    "day_of_week",
    "transaction_month",
    "use_chip",
    "mcc",
    "card_brand",
    "card_type",
    "has_chip",
]

EXTENDED_NUMERIC = [
    "credit_limit",
    "per_capita_income",
    "yearly_income",
    "total_debt",
    "credit_score",
    "amount_to_credit_limit",
    "amount_to_yearly_income",
]

CONFIGURATIONS = [
    {
        "configuration": "principal_amount_raw",
        "feature_set": "principal",
        "amount_variant": "raw",
    },
    {
        "configuration": "principal_amount_signed_log",
        "feature_set": "principal",
        "amount_variant": "signed_log",
    },
    {
        "configuration": "extended_amount_raw",
        "feature_set": "extended",
        "amount_variant": "raw",
    },
    {
        "configuration": "extended_amount_signed_log",
        "feature_set": "extended",
        "amount_variant": "signed_log",
    },
]


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
    parser.add_argument(
        "--sample-modulo",
        type=int,
        default=9,
        help="Aproximadamente una de cada N filas integra la muestra.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "models",
    )
    parser.add_argument(
        "--fetch-size",
        type=int,
        default=50_000,
        help="Filas leídas por bloque desde SQL Server.",
    )
    return parser.parse_args()


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


def required_source_columns() -> list[str]:
    return list(
        dict.fromkeys(BASE_NUMERIC + BASE_CATEGORICAL + EXTENDED_NUMERIC)
    )


def validate_schema(connection: Any) -> None:
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
    expected = {*required_source_columns(), "transaction_id", "is_fraud"}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "Faltan variables requeridas en la vista: " + ", ".join(missing)
        )


def load_sample(connection: Any, args: argparse.Namespace) -> Any:
    import numpy as np
    import pandas as pd

    selected = required_source_columns()
    columns_sql = ", ".join(quote_identifier(name) for name in selected)
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
    for column in BASE_NUMERIC + EXTENDED_NUMERIC:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["is_fraud"] = data["is_fraud"].astype("int8")
    amount = data["amount"].astype(float)
    data["amount_signed_log"] = np.sign(amount) * np.log1p(np.abs(amount))
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


def configuration_features(
    configuration: dict[str, str]
) -> tuple[list[str], list[str]]:
    numeric = list(BASE_NUMERIC)
    if configuration["amount_variant"] == "signed_log":
        numeric[numeric.index("amount")] = "amount_signed_log"
    if configuration["feature_set"] == "extended":
        numeric.extend(EXTENDED_NUMERIC)
    return numeric, list(BASE_CATEGORICAL)


def make_preprocessor(numeric: list[str], categorical: list[str]) -> Any:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
            ),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric),
            ("categorical", categorical_pipeline, categorical),
        ],
        sparse_threshold=1.0,
    )


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


def evaluate_configuration(
    data: Any,
    target: Any,
    train_indices: Any,
    validation_indices: Any,
    configuration: dict[str, str],
    seed: int,
) -> dict[str, Any]:
    from sklearn.metrics import (
        average_precision_score,
        confusion_matrix,
        precision_recall_fscore_support,
        roc_auc_score,
    )
    from xgboost import XGBClassifier

    numeric, categorical = configuration_features(configuration)
    features = numeric + categorical
    train_x = data.iloc[train_indices][features]
    validation_x = data.iloc[validation_indices][features]
    train_y = target.iloc[train_indices]
    validation_y = target.iloc[validation_indices]

    preprocessor = make_preprocessor(numeric, categorical)
    transformed_train = preprocessor.fit_transform(train_x)
    transformed_validation = preprocessor.transform(validation_x)
    negative = int((train_y == 0).sum())
    positive = int((train_y == 1).sum())
    class_ratio = negative / positive

    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.10,
        subsample=0.80,
        colsample_bytree=0.80,
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        scale_pos_weight=class_ratio,
        random_state=seed,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(transformed_train, train_y)
    probabilities = model.predict_proba(transformed_validation)[:, 1]
    threshold = best_f1_threshold(validation_y, probabilities)
    predictions = (probabilities >= threshold).astype("int8")
    precision, recall, f1, _ = precision_recall_fscore_support(
        validation_y,
        predictions,
        average="binary",
        zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(
        validation_y, predictions, labels=[0, 1]
    ).ravel()
    return {
        **configuration,
        "numeric_features": len(numeric),
        "categorical_features": len(categorical),
        "encoded_features": int(transformed_train.shape[1]),
        "validation_threshold": round(threshold, 8),
        "validation_precision": round(float(precision), 8),
        "validation_recall": round(float(recall), 8),
        "validation_f1": round(float(f1), 8),
        "validation_roc_auc": round(
            float(roc_auc_score(validation_y, probabilities)), 8
        ),
        "validation_pr_auc": round(
            float(average_precision_score(validation_y, probabilities)), 8
        ),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "test_used": "no",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No hay filas para guardar en {path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def package_versions() -> dict[str, str]:
    packages = [
        "numpy",
        "pandas",
        "pyodbc",
        "scikit-learn",
        "xgboost",
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def class_counts(target: Any, indices: Any) -> dict[str, int]:
    subset = target.iloc[indices]
    return {
        "rows": int(len(subset)),
        "frauds": int(subset.sum()),
        "non_frauds": int((subset == 0).sum()),
    }


def main() -> int:
    args = parse_args()
    if args.sample_modulo <= 0:
        raise ValueError("--sample-modulo debe ser positivo")
    if args.fetch_size <= 0:
        raise ValueError("--fetch-size debe ser positivo")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = connect(args)
    try:
        validate_schema(connection)
        data = load_sample(connection, args)
    finally:
        connection.close()

    target = data["is_fraud"]
    train_indices, validation_indices, test_indices = split_indices(
        target, args.seed
    )
    split_summary = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    print("División estratificada preparada:")
    for name, values in split_summary.items():
        print(f"- {name}: {values['rows']:,} filas; {values['frauds']:,} fraudes")

    results = []
    for position, configuration in enumerate(CONFIGURATIONS, start=1):
        print(
            f"Comparando {position}/4: {configuration['configuration']}"
        )
        result = evaluate_configuration(
            data,
            target,
            train_indices,
            validation_indices,
            configuration,
            args.seed,
        )
        results.append(result)
        print(
            f"  PR-AUC={result['validation_pr_auc']:.6f}; "
            f"F1={result['validation_f1']:.6f}; "
            f"Recall={result['validation_recall']:.6f}; "
            f"Precision={result['validation_precision']:.6f}"
        )

    ordered = sorted(
        results,
        key=lambda row: (
            row["validation_pr_auc"],
            row["validation_f1"],
            row["validation_recall"],
        ),
        reverse=True,
    )
    winner = ordered[0]
    winner_config = next(
        item
        for item in CONFIGURATIONS
        if item["configuration"] == winner["configuration"]
    )
    winner_numeric, winner_categorical = configuration_features(winner_config)

    write_csv(output_dir / "feature_configuration_comparison.csv", results)
    selected = {
        "configuration": winner["configuration"],
        "selection_rule": "highest_validation_pr_auc_then_f1_then_recall",
        "numeric_features": winner_numeric,
        "categorical_features": winner_categorical,
        "validation_threshold": winner["validation_threshold"],
        "test_used": False,
    }
    (output_dir / "feature_configuration_selected.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "database": args.database,
        "seed": args.seed,
        "sample_modulo": args.sample_modulo,
        "sample_rows": int(len(data)),
        "sample_frauds": int(target.sum()),
        "split": split_summary,
        "configurations_compared": len(CONFIGURATIONS),
        "screening_model": (
            "XGBoost común a las cuatro configuraciones con ponderación "
            "de clase; no corresponde al experimento final de balanceo."
        ),
        "test_policy": (
            "El conjunto de prueba fue separado y contado, pero no fue "
            "transformado, predicho ni utilizado para seleccionar variables."
        ),
        "package_versions": package_versions(),
    }
    (output_dir / "feature_configuration_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Configuración seleccionada: {winner['configuration']}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
