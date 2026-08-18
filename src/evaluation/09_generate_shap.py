"""Genera explicaciones SHAP globales y locales sin utilizar el test final."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
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
    parser.add_argument("--max-global-rows", type=int, default=1_000)
    parser.add_argument("--top-features", type=int, default=20)
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "shap",
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


def load_development_sample(
    connection: Any,
    args: argparse.Namespace,
    ordered_features: list[str],
    numeric_features: list[str],
) -> Any:
    import pandas as pd

    columns_sql = ", ".join(
        quote_identifier(name) for name in ordered_features
    )
    query = f"""
        SELECT transaction_id, {columns_sql}, is_fraud
        FROM dbo.vw_dataset_maestro
        WHERE (CHECKSUM(transaction_id, {int(args.seed)}) & 2147483647)
              % {int(args.sample_modulo)} = 0
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
        print(f"Datos leidos para SHAP: {loaded:,} filas", flush=True)
    cursor.close()
    if not blocks:
        raise RuntimeError("La muestra para SHAP quedo vacia")
    data = pd.concat(blocks, ignore_index=True)
    for column in numeric_features:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["is_fraud"] = data["is_fraud"].astype("int8")
    return data


def validation_indices(target: Any, seed: int) -> Any:
    import numpy as np
    from sklearn.model_selection import train_test_split

    all_indices = np.arange(len(target))
    _, temporary_indices = train_test_split(
        all_indices,
        test_size=0.30,
        random_state=seed,
        stratify=target,
    )
    validation, _ = train_test_split(
        temporary_indices,
        test_size=0.50,
        random_state=seed,
        stratify=target.iloc[temporary_indices],
    )
    return validation


def choose_explanation_rows(
    validation_data: Any, max_rows: int, seed: int
) -> Any:
    import pandas as pd

    fraud = validation_data[validation_data["is_fraud"] == 1]
    non_fraud = validation_data[validation_data["is_fraud"] == 0]
    fraud_count = min(len(fraud), max_rows // 2)
    non_fraud_count = min(len(non_fraud), max_rows - fraud_count)
    selected_fraud = fraud.sample(n=fraud_count, random_state=seed)
    selected_non_fraud = non_fraud.sample(
        n=non_fraud_count, random_state=seed
    )
    return (
        pd.concat([selected_fraud, selected_non_fraud])
        .sample(frac=1, random_state=seed)
        .reset_index(drop=True)
    )


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
    """Recupera nombres comprensibles tras OrdinalEncoder + OneHotEncoder."""
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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def global_plot(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = rows[:20][::-1]
    figure, axis = plt.subplots(figsize=(11, 7))
    axis.barh(
        [row["feature"] for row in selected],
        [row["mean_absolute_shap"] for row in selected],
        color="#1f77b4",
    )
    axis.set_xlabel("Importancia SHAP media absoluta")
    axis.set_title("Factores generales de la prediccion de fraude")
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def local_plot(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = rows[:10][::-1]
    colors = [
        "#d62728" if row["shap_value"] > 0 else "#2ca02c"
        for row in selected
    ]
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.barh(
        [row["feature"] for row in selected],
        [row["shap_value"] for row in selected],
        color=colors,
    )
    axis.axvline(0, color="black", linewidth=0.8)
    axis.set_xlabel("Aporte SHAP a la prediccion")
    axis.set_title("Explicacion local de una transaccion")
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    if args.max_global_rows < 20 or args.top_features < 5:
        raise ValueError("La muestra SHAP o la cantidad de factores es muy baja")
    model_path = args.model_file.resolve()
    schema_path = args.schema_file.resolve()
    if not model_path.exists() or not schema_path.exists():
        raise FileNotFoundError(
            "Primero debe entrenarse y exportarse el modelo final"
        )
    schema = read_json(schema_path)
    if schema.get("test_used") is not False:
        raise ValueError("El esquema no confirma que el test siga reservado")
    actual_hash = sha256(model_path)
    if schema.get("model_sha256") != actual_hash:
        raise ValueError("El hash del pipeline no coincide con el esquema")

    ordered_features = list(schema["ordered_features"])
    numeric_features = list(schema["numeric_features"])
    categorical_features = list(schema["categorical_features"])
    if ordered_features != numeric_features + categorical_features:
        raise ValueError("El orden de variables del esquema es inconsistente")

    import joblib
    import numpy as np
    import shap

    pipeline = joblib.load(model_path)
    preprocessor = pipeline.named_steps["preprocessor"]
    model = pipeline.named_steps["model"]
    connection = connect(args)
    try:
        data = load_development_sample(
            connection,
            args,
            ordered_features,
            numeric_features,
        )
    finally:
        connection.close()
    indices = validation_indices(data["is_fraud"], args.seed)
    validation = data.iloc[indices].copy()
    selected = choose_explanation_rows(
        validation, args.max_global_rows, args.seed
    )
    selected_ids = selected["transaction_id"].copy()
    selected_target = selected["is_fraud"].copy()
    transformed = preprocessor.transform(selected[ordered_features])
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    transformed = np.asarray(transformed, dtype="float32")
    feature_names = readable_feature_names(
        preprocessor, numeric_features, categorical_features
    )
    if transformed.shape[1] != len(feature_names):
        raise ValueError("No coincide la matriz transformada con sus nombres")

    explainer = shap.TreeExplainer(model)
    shap_matrix = positive_class_shap(explainer.shap_values(transformed))
    if shap_matrix.shape != transformed.shape:
        raise ValueError("La salida SHAP no coincide con la matriz explicada")
    global_values = np.mean(np.abs(shap_matrix), axis=0)
    global_rows = sorted(
        [
            {
                "feature": feature_names[index],
                "mean_absolute_shap": round(float(value), 10),
            }
            for index, value in enumerate(global_values)
        ],
        key=lambda row: row["mean_absolute_shap"],
        reverse=True,
    )

    probabilities = pipeline.predict_proba(selected[ordered_features])[:, 1]
    fraud_positions = np.flatnonzero(selected_target.to_numpy() == 1)
    if fraud_positions.size:
        local_position = int(
            fraud_positions[np.argmax(probabilities[fraud_positions])]
        )
    else:
        local_position = int(np.argmax(probabilities))
    local_rows = sorted(
        [
            {
                "feature": feature_names[index],
                "feature_value": round(
                    float(transformed[local_position, index]), 8
                ),
                "shap_value": round(
                    float(shap_matrix[local_position, index]), 10
                ),
            }
            for index in range(len(feature_names))
        ],
        key=lambda row: abs(row["shap_value"]),
        reverse=True,
    )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "shap_global_importance.csv", global_rows)
    write_csv(output_dir / "shap_local_explanation.csv", local_rows)
    global_plot(
        global_rows[: args.top_features],
        output_dir / "shap_global_summary.png",
    )
    local_plot(local_rows, output_dir / "shap_local_example.png")
    metadata = {
        "model_file": model_path.name,
        "model_sha256": actual_hash,
        "source_partition": "validation_development_only",
        "explained_rows": int(len(selected)),
        "explained_frauds": int(selected_target.sum()),
        "local_transaction_id": int(selected_ids.iloc[local_position]),
        "local_true_label": int(selected_target.iloc[local_position]),
        "local_probability": round(float(probabilities[local_position]), 10),
        "top_features": args.top_features,
        "test_used": False,
        "note": (
            "Las explicaciones se generaron con registros de desarrollo; "
            "el test final no fue cargado ni utilizado."
        ),
    }
    (output_dir / "shap_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"SHAP generado para {len(selected):,} registros de desarrollo.")
    print(f"Explicacion local: transaccion {selected_ids.iloc[local_position]}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba no fue utilizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
