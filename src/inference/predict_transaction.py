"""Predice una transaccion con el pipeline FINAN y responde en JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--transaction-id", type=int)
    source.add_argument("--input-json", type=Path)
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
    parser.add_argument(
        "--model-file",
        type=Path,
        default=root / "models" / "finan_fraud_pipeline.joblib",
    )
    parser.add_argument(
        "--schema-file",
        type=Path,
        default=root / "models" / "finan_feature_schema.json",
    )
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--top-factors", type=int, default=5)
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Muestra el JSON con sangría para facilitar su lectura manual.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no valido: {name}")
    return f"[{name}]"


def load_from_database(
    args: argparse.Namespace, ordered_features: list[str]
) -> dict[str, Any]:
    import pyodbc

    columns_sql = ", ".join(
        quote_identifier(name) for name in ordered_features
    )
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(
        connection_string, autocommit=True, timeout=30
    )
    try:
        cursor = connection.execute(
            f"SELECT {columns_sql} FROM dbo.vw_dataset_maestro "
            "WHERE transaction_id = ?",
            int(args.transaction_id),
        )
        rows = cursor.fetchall()
        if not rows:
            raise LookupError(
                f"No existe la transaccion {args.transaction_id}"
            )
        if len(rows) != 1:
            raise RuntimeError("El transaction_id no es unico")
        return dict(zip(ordered_features, rows[0], strict=True))
    finally:
        connection.close()


def validate_input(
    values: dict[str, Any],
    ordered_features: list[str],
    numeric_features: list[str],
) -> dict[str, Any]:
    missing = [name for name in ordered_features if name not in values]
    if missing:
        raise ValueError("Faltan variables: " + ", ".join(missing))
    clean = {name: values[name] for name in ordered_features}
    for name in numeric_features:
        value = clean[name]
        if value is not None:
            clean[name] = float(value)
    return clean


def positive_class_shap(values: Any) -> Any:
    import numpy as np

    if isinstance(values, list):
        return np.asarray(values[-1])
    array = np.asarray(values)
    if array.ndim == 3:
        return array[:, :, -1]
    if array.ndim != 2:
        raise ValueError(f"Forma SHAP no esperada: {array.shape}")
    return array


def readable_feature_names(
    preprocessor: Any,
    numeric_features: list[str],
    categorical_features: list[str],
) -> list[str]:
    names = list(numeric_features)
    categorical_pipeline = preprocessor.named_transformers_["categorical"]
    ordinal = categorical_pipeline.named_steps["ordinal"]
    onehot = categorical_pipeline.named_steps["onehot"]
    for feature, original_values, encoded_values in zip(
        categorical_features,
        ordinal.categories_,
        onehot.categories_,
        strict=True,
    ):
        for encoded_value in encoded_values:
            encoded_index = int(round(float(encoded_value)))
            if (
                encoded_index < 0
                or encoded_index >= len(original_values)
                or float(encoded_value) != float(encoded_index)
            ):
                displayed_value = str(encoded_value)
            else:
                displayed_value = str(original_values[encoded_index])
            names.append(f"{feature}={displayed_value}")
    return names


def explain_row(
    pipeline: Any,
    frame: Any,
    top_factors: int,
    numeric_features: list[str],
    categorical_features: list[str],
) -> list[dict[str, Any]]:
    import numpy as np
    import shap

    preprocessor = pipeline.named_steps["preprocessor"]
    model = pipeline.named_steps["model"]
    transformed = preprocessor.transform(frame)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    transformed = np.asarray(transformed, dtype="float32")
    feature_names = readable_feature_names(
        preprocessor, numeric_features, categorical_features
    )
    explainer = shap.TreeExplainer(model)
    shap_matrix = positive_class_shap(explainer.shap_values(transformed))
    rows = sorted(
        [
            {
                "feature": feature_names[index],
                "value": round(float(transformed[0, index]), 8),
                "contribution": round(float(shap_matrix[0, index]), 10),
            }
            for index in range(len(feature_names))
        ],
        key=lambda row: abs(row["contribution"]),
        reverse=True,
    )
    return rows[:top_factors]


def risk_level(probability: float, threshold: float) -> str:
    if probability >= threshold:
        return "alto"
    if probability >= threshold * 0.5:
        return "medio"
    return "bajo"


def main() -> int:
    args = parse_args()
    if args.top_factors <= 0:
        raise ValueError("top-factors debe ser positivo")
    model_path = args.model_file.resolve()
    schema_path = args.schema_file.resolve()
    if not model_path.exists() or not schema_path.exists():
        raise FileNotFoundError("No existe el pipeline final o su esquema")
    schema = read_json(schema_path)
    if schema.get("test_used") is not False:
        raise ValueError("El esquema del modelo es inconsistente")
    model_hash = sha256(model_path)
    if schema.get("model_sha256") != model_hash:
        raise ValueError("El pipeline no coincide con su esquema")
    ordered_features = list(schema["ordered_features"])
    numeric_features = list(schema["numeric_features"])
    categorical_features = list(schema["categorical_features"])
    if ordered_features != numeric_features + categorical_features:
        raise ValueError("El orden de variables del esquema es inconsistente")

    if args.input_json:
        raw_values = read_json(args.input_json)
        source = "new_transaction"
        identifier: int | str = "new"
    else:
        raw_values = load_from_database(args, ordered_features)
        source = "database"
        identifier = int(args.transaction_id)
    values = validate_input(
        raw_values,
        ordered_features,
        numeric_features,
    )

    import joblib
    import pandas as pd

    pipeline = joblib.load(model_path)
    frame = pd.DataFrame([values], columns=ordered_features)
    probability = float(pipeline.predict_proba(frame)[0, 1])
    threshold = float(schema["threshold"])
    response = {
        "status": "ok",
        "source": source,
        "transaction_id": identifier,
        "fraud_probability": round(probability, 10),
        "threshold": round(threshold, 10),
        "is_fraud_prediction": bool(probability >= threshold),
        "risk_level": risk_level(probability, threshold),
        "model_sha256": model_hash,
        "top_factors": (
            explain_row(
                pipeline,
                frame,
                args.top_factors,
                numeric_features,
                categorical_features,
            )
            if args.explain
            else []
        ),
    }
    print(
        json.dumps(
            response,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
