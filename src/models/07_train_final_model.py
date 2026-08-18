"""Entrena y guarda el pipeline final de FINAN sin utilizar el test reservado.

Lee la configuracion refinada de Random Forest, reconstruye la misma muestra
deterministica y reproduce la division estratificada 70/15/15. Une solamente
entrenamiento y validacion para el ajuste final. El 15 % de test se separa,
cuenta y excluye del preprocesamiento y del entrenamiento.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


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
        "--tree-step",
        type=int,
        default=10,
        help="Cantidad de arboles agregados antes de informar el avance.",
    )
    parser.add_argument(
        "--refinement-selection-file",
        type=Path,
        default=root / "results" / "models" / "rf_refinement_selected.json",
    )
    parser.add_argument(
        "--feature-selection-file",
        type=Path,
        default=(
            root
            / "results"
            / "models"
            / "feature_configuration_selected.json"
        ),
    )
    parser.add_argument(
        "--reference-metadata-file",
        type=Path,
        default=root / "results" / "models" / "final_candidate_metadata.json",
    )
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
        "--metadata-file",
        type=Path,
        default=(
            root
            / "results"
            / "models"
            / "final_model_training_metadata.json"
        ),
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un objeto JSON en {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no valido: {name}")
    return f"[{name}]"


def read_configuration(
    args: argparse.Namespace,
) -> tuple[list[str], list[str], dict[str, Any], float]:
    features = read_json(args.feature_selection_file)
    numeric = list(features.get("numeric_features", []))
    categorical = list(features.get("categorical_features", []))
    ordered = numeric + categorical
    if not numeric or not categorical:
        raise ValueError("La seleccion no contiene variables numericas y categoricas")
    if len(ordered) != len(set(ordered)):
        raise ValueError("La seleccion contiene variables duplicadas")
    if "is_fraud" in ordered or "transaction_id" in ordered:
        raise ValueError("La etiqueta y el identificador no pueden ser predictores")
    if features.get("test_used") is not False:
        raise ValueError("La seleccion de variables no confirma el test reservado")

    refinement = read_json(args.refinement_selection_file)
    refinement_candidate = str(refinement.get("candidate", ""))
    if not (
        refinement_candidate == "random_forest"
        or refinement_candidate.startswith("rf_")
    ):
        raise ValueError("El refinamiento seleccionado no corresponde a Random Forest")
    if refinement.get("test_used") is not False:
        raise ValueError("El refinamiento no confirma el test reservado")
    parameters = refinement.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("El refinamiento no contiene parametros del modelo")
    threshold = float(refinement["validation_threshold"])
    if not 0.0 < threshold < 1.0:
        raise ValueError("El umbral de validacion debe estar entre 0 y 1")
    return numeric, categorical, dict(parameters), threshold


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

    ordered = numeric + categorical
    columns_sql = ", ".join(quote_identifier(name) for name in ordered)
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


def verify_reference(
    path: Path, sample_rows: int, split_summary: dict[str, Any]
) -> None:
    if not path.exists():
        raise FileNotFoundError(f"No existe la metadata de referencia: {path}")
    reference = read_json(path)
    if int(reference.get("sample_rows", -1)) != sample_rows:
        raise RuntimeError("La muestra no coincide con la comparacion de candidatos")
    expected_split = reference.get("split")
    if expected_split != split_summary:
        raise RuntimeError("La division no coincide con la comparacion de candidatos")
    policy = str(reference.get("test_policy", "")).lower()
    if "reserv" not in policy or "no fue" not in policy:
        raise ValueError("La metadata de referencia no confirma el test reservado")


def build_preprocessor(
    numeric: list[str], categorical: list[str]
) -> Any:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "ordinal",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
            ),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric),
            ("categorical", categorical_pipeline, categorical),
        ],
        sparse_threshold=1.0,
        verbose_feature_names_out=False,
    )


def normalize_rf_parameters(
    selected: dict[str, Any], seed: int
) -> tuple[dict[str, Any], int]:
    from sklearn.ensemble import RandomForestClassifier

    allowed = set(RandomForestClassifier().get_params(deep=False))
    unknown = sorted(set(selected) - allowed)
    if unknown:
        raise ValueError(
            "Parametros no reconocidos para Random Forest: " + ", ".join(unknown)
        )
    parameters = dict(selected)
    total_trees = int(parameters.get("n_estimators", 0))
    if total_trees <= 0:
        raise ValueError("El refinamiento debe seleccionar n_estimators positivo")
    parameters["n_estimators"] = total_trees
    parameters["random_state"] = seed
    parameters["n_jobs"] = -1
    parameters["warm_start"] = True
    return parameters, total_trees


def train_random_forest(
    matrix: Any,
    target: Any,
    parameters: dict[str, Any],
    total_trees: int,
    tree_step: int,
) -> tuple[Any, float]:
    from sklearn.ensemble import RandomForestClassifier

    model = RandomForestClassifier(**parameters)
    checkpoints = list(range(tree_step, total_trees, tree_step))
    checkpoints.append(total_trees)
    started = perf_counter()
    for current_trees in checkpoints:
        model.set_params(n_estimators=current_trees)
        model.fit(matrix, target)
        percentage = 35 + round(55 * current_trees / total_trees)
        print(
            f"Arboles: {current_trees:,}/{total_trees:,} "
            f"({percentage} % de avance general)",
            flush=True,
        )
    elapsed = perf_counter() - started
    model.set_params(warm_start=False)
    return model, elapsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.resolve().open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    if args.sample_modulo <= 0 or args.fetch_size <= 0 or args.tree_step <= 0:
        raise ValueError("Muestra, bloques y paso de arboles deben ser positivos")

    print("Progreso general: 0 % - inicio", flush=True)
    numeric, categorical, selected_parameters, threshold = read_configuration(
        args
    )
    connection = connect(args)
    try:
        validate_schema(connection, numeric, categorical)
        data = load_sample(connection, args, numeric, categorical)
    finally:
        connection.close()
    print("Progreso general: 15 % - muestra reconstruida", flush=True)

    import joblib
    import numpy as np
    from sklearn.pipeline import Pipeline

    target = data["is_fraud"]
    train_indices, validation_indices, test_indices = split_indices(
        target, args.seed
    )
    split_summary = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    verify_reference(args.reference_metadata_file, len(data), split_summary)
    development_indices = np.concatenate([train_indices, validation_indices])
    ordered_features = numeric + categorical
    development_data = data.iloc[development_indices][ordered_features]
    development_target = target.iloc[development_indices]
    development_summary = class_counts(target, development_indices)
    del data, target, train_indices, validation_indices, development_indices
    print(
        "Progreso general: 25 % - train y validacion unidos; test excluido",
        flush=True,
    )

    preprocessor = build_preprocessor(numeric, categorical)
    matrix = preprocessor.fit_transform(development_data)
    del development_data
    print(
        f"Matriz final: {matrix.shape[0]:,} filas y {matrix.shape[1]:,} columnas",
        flush=True,
    )
    print("Progreso general: 35 % - preprocesamiento ajustado", flush=True)

    training_parameters, total_trees = normalize_rf_parameters(
        selected_parameters, args.seed
    )
    model, training_seconds = train_random_forest(
        matrix,
        development_target,
        training_parameters,
        total_trees,
        args.tree_step,
    )
    pipeline = Pipeline(
        [("preprocessor", preprocessor), ("model", model)]
    )

    pipeline_path = args.pipeline_file.resolve()
    pipeline_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, pipeline_path, compress=3)
    model_sha256 = sha256_file(pipeline_path)
    print("Progreso general: 94 % - pipeline guardado", flush=True)

    schema = {
        "numeric_features": numeric,
        "categorical_features": categorical,
        "ordered_features": ordered_features,
        "threshold": threshold,
        "model_sha256": model_sha256,
        "test_used": False,
    }
    write_json(args.schema_file, schema)

    parameters_saved = model.get_params(deep=False)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": args.database,
        "seed": args.seed,
        "sample_modulo": args.sample_modulo,
        "sample_rows": int(sum(item["rows"] for item in split_summary.values())),
        "split": split_summary,
        "final_training": development_summary,
        "candidate": "random_forest",
        "selection_file": args.refinement_selection_file.name,
        "selected_parameters": selected_parameters,
        "training_parameters": parameters_saved,
        "training_seconds": round(float(training_seconds), 4),
        "preprocessing": {
            "numeric_imputation": "median",
            "numeric_scaling": "standard",
            "categorical_imputation": "most_frequent",
            "categorical_encoding": "ordinal_then_one_hot",
            "matrix_columns": int(matrix.shape[1]),
        },
        "validation_threshold": threshold,
        "threshold_policy": (
            "Se conserva el umbral elegido durante el refinamiento con "
            "validacion; no se recalcula con el test."
        ),
        "test_used": False,
        "test_policy": (
            "El test se separo con el mismo split, pero se excluyo del "
            "preprocesamiento y del entrenamiento final."
        ),
        "pipeline_file": pipeline_path.name,
        "schema_file": args.schema_file.resolve().name,
        "model_sha256": model_sha256,
        "pipeline_steps": ["preprocessor", "model"],
        "package_versions": package_versions(),
    }
    write_json(args.metadata_file, metadata)
    print("Progreso general: 100 % - artefactos finales guardados", flush=True)
    print(f"Pipeline: {pipeline_path}")
    print(f"SHA-256: {model_sha256}")
    print("El conjunto de prueba permanece reservado y no fue utilizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
