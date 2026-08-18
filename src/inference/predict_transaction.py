"""Predice una transaccion con el pipeline FINAN y responde en JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--transaction-id", type=int)
    source.add_argument("--input-json", type=Path)
    source.add_argument(
        "--new-transaction-json",
        type=Path,
        help=(
            "JSON con client_id, card_id, amount, transaction_date, "
            "use_chip y mcc. Las demás variables se obtienen desde FraudeDB."
        ),
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
    with path.resolve().open("r", encoding="utf-8-sig") as stream:
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


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    return float(cleaned) if cleaned else None


def parse_month_year(value: Any, field: str) -> tuple[int, int]:
    parts = str(value or "").strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Formato inválido en {field}; se esperaba MM/AAAA")
    month, year = int(parts[0]), int(parts[1])
    if month < 1 or month > 12 or year < 1900:
        raise ValueError(f"Fecha inválida en {field}")
    return month, year


def load_new_transaction(
    args: argparse.Namespace,
    ordered_features: list[str],
) -> dict[str, Any]:
    import pyodbc

    raw = read_json(args.new_transaction_json)
    required = (
        "client_id",
        "card_id",
        "amount",
        "transaction_date",
        "use_chip",
        "mcc",
    )
    missing = [name for name in required if raw.get(name) in (None, "")]
    if missing:
        raise ValueError("Faltan datos de la nueva transacción: " + ", ".join(missing))

    client_id = int(raw["client_id"])
    card_id = int(raw["card_id"])
    amount = parse_money(raw["amount"])
    if amount is None:
        raise ValueError("El monto de la nueva transacción no es válido")
    transaction_date = datetime.fromisoformat(
        str(raw["transaction_date"]).replace("Z", "+00:00")
    ).replace(tzinfo=None)

    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(connection_string, autocommit=True, timeout=30)
    try:
        row = connection.execute(
            """
            SELECT
                u.birth_year, u.birth_month, u.per_capita_income,
                u.yearly_income, u.total_debt, u.credit_score,
                u.num_credit_cards, c.card_brand, c.card_type, c.has_chip,
                c.num_cards_issued, c.credit_limit, c.acct_open_date,
                c.year_pin_last_changed, c.expires
            FROM dbo.cards_data AS c
            INNER JOIN dbo.users_data AS u ON u.id = c.client_id
            WHERE c.id = ? AND c.client_id = ?
            """,
            card_id,
            client_id,
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise LookupError("La tarjeta no existe o no pertenece al cliente indicado")

    (
        birth_year,
        birth_month,
        per_capita_income,
        yearly_income,
        total_debt,
        credit_score,
        num_credit_cards,
        card_brand,
        card_type,
        has_chip,
        num_cards_issued,
        credit_limit,
        account_open_date,
        year_pin_last_changed,
        expires,
    ) = row
    yearly_income_value = parse_money(yearly_income)
    credit_limit_value = parse_money(credit_limit)
    open_month, open_year = parse_month_year(account_open_date, "acct_open_date")
    expiration_month, expiration_year = parse_month_year(expires, "expires")

    age_at_transaction = None
    if birth_year is not None:
        age_at_transaction = transaction_date.year - int(birth_year)
        if birth_month is not None and transaction_date.month < int(birth_month):
            age_at_transaction -= 1
    years_since_pin_change = None
    if year_pin_last_changed is not None and int(year_pin_last_changed) <= transaction_date.year:
        years_since_pin_change = transaction_date.year - int(year_pin_last_changed)

    values = {
        "amount": amount,
        "age_at_transaction": age_at_transaction,
        "num_credit_cards": num_credit_cards,
        "num_cards_issued": num_cards_issued,
        "card_account_age_years": (
            ((transaction_date.year - open_year) * 12 + transaction_date.month - open_month)
            / 12.0
        ),
        "months_to_card_expiration": (
            (expiration_year - transaction_date.year) * 12
            + expiration_month
            - transaction_date.month
        ),
        "years_since_pin_change": years_since_pin_change,
        "credit_limit": credit_limit_value,
        "per_capita_income": parse_money(per_capita_income),
        "yearly_income": yearly_income_value,
        "total_debt": parse_money(total_debt),
        "credit_score": credit_score,
        "amount_to_credit_limit": (
            amount / credit_limit_value if credit_limit_value not in (None, 0) else None
        ),
        "amount_to_yearly_income": (
            amount / yearly_income_value if yearly_income_value not in (None, 0) else None
        ),
        "transaction_hour": transaction_date.hour,
        "day_of_week": transaction_date.weekday() + 1,
        "transaction_month": transaction_date.month,
        "use_chip": str(raw["use_chip"]),
        "mcc": int(raw["mcc"]),
        "card_brand": card_brand,
        "card_type": card_type,
        "has_chip": has_chip,
    }
    return {name: values[name] for name in ordered_features}


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

    if args.new_transaction_json:
        raw_values = load_new_transaction(args, ordered_features)
        source = "new_transaction"
        identifier: int | str = "new"
    elif args.input_json:
        raw_values = read_json(args.input_json)
        source = "new_transaction"
        identifier = "new"
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
