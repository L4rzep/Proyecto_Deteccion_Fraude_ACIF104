"""Genera referencias y una muestra segura a partir de FraudeDB real."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import pyodbc


SOURCE_FILES = [
    "transactions_data.csv",
    "users_data.csv",
    "cards_data.csv",
    "train_fraud_labels.json",
    "mcc_codes.json",
]
FILE_TO_TABLE = {
    "transactions_data.csv": "transactions_data",
    "users_data.csv": "users_data",
    "cards_data.csv": "cards_data",
    "train_fraud_labels.json": "fraud_labels",
    "mcc_codes.json": "mcc_codes",
}
KEY_COLUMNS = {
    ("transactions_data", "id"),
    ("users_data", "id"),
    ("cards_data", "id"),
    ("fraud_labels", "transaction_id"),
    ("mcc_codes", "mcc"),
}
MONEY_COLUMNS = {
    ("transactions_data", "amount"),
    ("users_data", "per_capita_income"),
    ("users_data", "yearly_income"),
    ("users_data", "total_debt"),
    ("cards_data", "credit_limit"),
}
LABEL_PATTERN = re.compile(r'"\d+"\s*:\s*"(?:Yes|No)"')

DESCRIPTIONS = {
    ("transactions_data", "id"): "Identificador único de la transacción.",
    ("transactions_data", "date"): "Fecha y hora registradas para la transacción.",
    ("transactions_data", "client_id"): "Identificador del cliente asociado.",
    ("transactions_data", "card_id"): "Identificador de la tarjeta asociada.",
    ("transactions_data", "amount"): "Monto registrado por la transacción.",
    ("transactions_data", "use_chip"): "Canal o mecanismo de uso de la tarjeta.",
    ("transactions_data", "merchant_id"): "Identificador del comercio.",
    ("transactions_data", "merchant_city"): "Ciudad registrada para el comercio.",
    ("transactions_data", "merchant_state"): "Estado o región registrada para el comercio.",
    ("transactions_data", "zip"): "Código postal registrado para el comercio.",
    ("transactions_data", "mcc"): "Código de categoría del comercio.",
    ("transactions_data", "errors"): "Semántica exacta y momento de disponibilidad por confirmar.",
    ("users_data", "id"): "Identificador del cliente.",
    ("users_data", "current_age"): "Edad incluida en la fuente; fecha de referencia por confirmar.",
    ("users_data", "retirement_age"): "Edad de retiro registrada.",
    ("users_data", "birth_year"): "Año de nacimiento registrado.",
    ("users_data", "birth_month"): "Mes de nacimiento registrado.",
    ("users_data", "gender"): "Categoría de género incluida en la fuente.",
    ("users_data", "address"): "Domicilio incluido en la fuente.",
    ("users_data", "latitude"): "Latitud asociada al cliente.",
    ("users_data", "longitude"): "Longitud asociada al cliente.",
    ("users_data", "per_capita_income"): "Ingreso per cápita incluido en la fuente.",
    ("users_data", "yearly_income"): "Ingreso anual incluido en la fuente.",
    ("users_data", "total_debt"): "Deuda total incluida en la fuente.",
    ("users_data", "credit_score"): "Puntaje crediticio incluido en la fuente.",
    ("users_data", "num_credit_cards"): "Cantidad de tarjetas de crédito registrada.",
    ("cards_data", "id"): "Identificador de la tarjeta.",
    ("cards_data", "client_id"): "Identificador del titular asociado.",
    ("cards_data", "card_brand"): "Marca de la tarjeta.",
    ("cards_data", "card_type"): "Tipo de tarjeta.",
    ("cards_data", "card_number"): "Número completo de tarjeta; dato sensible excluido.",
    ("cards_data", "expires"): "Mes y año de expiración registrados.",
    ("cards_data", "cvv"): "Código de verificación; dato sensible excluido.",
    ("cards_data", "has_chip"): "Indicador de disponibilidad de chip.",
    ("cards_data", "num_cards_issued"): "Cantidad de tarjetas emitidas para la cuenta.",
    ("cards_data", "credit_limit"): "Límite de crédito registrado.",
    ("cards_data", "acct_open_date"): "Mes y año de apertura de la cuenta.",
    ("cards_data", "year_pin_last_changed"): "Año del último cambio de PIN registrado.",
    ("cards_data", "card_on_dark_web"): "Indicador de la fuente; disponibilidad temporal por confirmar.",
    ("fraud_labels", "transaction_id"): "Identificador de la transacción etiquetada.",
    ("fraud_labels", "is_fraud"): "Etiqueta binaria de fraude.",
    ("mcc_codes", "mcc"): "Código de categoría del comercio.",
    ("mcc_codes", "description"): "Descripción del código MCC.",
}

DERIVED_FIELDS = [
    ("transaction_hour", "Hora derivada de transaction_date."),
    ("day_of_week", "Día de semana derivado de transaction_date; lunes=1."),
    ("is_weekend", "Indicador derivado de sábado o domingo."),
    ("transaction_month", "Mes derivado de transaction_date."),
    ("age_at_transaction", "Edad aproximada derivada para la fecha de transacción."),
    ("amount_to_credit_limit", "Monto dividido por límite de crédito."),
    ("amount_to_yearly_income", "Monto dividido por ingreso anual."),
    ("card_account_age_years", "Antigüedad aproximada de la cuenta en años."),
    ("months_to_card_expiration", "Meses entre transacción y expiración de la tarjeta."),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=os.getenv("FINAN_SOURCE_DIR"),
        required=os.getenv("FINAN_SOURCE_DIR") is None,
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
    parser.add_argument("--driver-version", default="por confirmar")
    parser.add_argument(
        "--snapshot-version", default="finan-1500k-seed42-v1"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reference-dir", type=Path, default=Path("data/reference"))
    parser.add_argument("--sample-dir", type=Path, default=Path("data/sample"))
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=True)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count_csv_rows(path: Path) -> int:
    line_count = 0
    last = b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            line_count += block.count(b"\n")
            last = block[-1:]
    if last and last != b"\n":
        line_count += 1
    return max(0, line_count - 1)


def count_label_rows(path: Path) -> int:
    total = 0
    carry = ""
    with path.open("r", encoding="utf-8") as stream:
        while True:
            chunk = stream.read(1_048_576)
            if not chunk:
                break
            parts = (carry + chunk).split(",")
            carry = parts.pop()
            total += sum(len(LABEL_PATTERN.findall(part)) for part in parts)
    total += len(LABEL_PATTERN.findall(carry))
    return total


def source_row_count(path: Path) -> int:
    if path.suffix.lower() == ".csv":
        return count_csv_rows(path)
    if path.name == "train_fraud_labels.json":
        return count_label_rows(path)
    with path.open("r", encoding="utf-8") as stream:
        return len(json.load(stream))


def snapshot_hash(connection: pyodbc.Connection, version: str) -> str:
    digest = hashlib.sha256()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT transaction_id, split, seed
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?
        ORDER BY transaction_id;
        """,
        version,
    )
    while True:
        rows = cursor.fetchmany(50_000)
        if not rows:
            break
        for transaction_id, split_name, seed in rows:
            digest.update(
                f"{int(transaction_id)}|{split_name}|{int(seed)}\n".encode(
                    "utf-8"
                )
            )
    cursor.close()
    return digest.hexdigest()


def schema_rows(connection: pyodbc.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE,
               IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME IN
              ('transactions_data','users_data','cards_data','fraud_labels','mcc_codes')
        ORDER BY TABLE_NAME, ORDINAL_POSITION;
        """
    ).fetchall()
    output = []
    for row in rows:
        table, position, column, data_type, length, precision, scale, nullable = row
        if length is not None:
            rendered_type = f"{data_type}({length})"
        elif precision is not None and data_type in {"decimal", "numeric"}:
            rendered_type = f"{data_type}({precision},{scale})"
        else:
            rendered_type = str(data_type)
        output.append(
            {
                "source_table": str(table),
                "ordinal_position": int(position),
                "column_name": str(column),
                "data_type": rendered_type,
                "base_type": str(data_type),
                "nullable": str(nullable),
            }
        )
    return output


def data_dictionary(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identifiers = {
        ("transactions_data", "id"),
        ("transactions_data", "client_id"),
        ("transactions_data", "card_id"),
        ("transactions_data", "merchant_id"),
        ("users_data", "id"),
        ("cards_data", "id"),
        ("cards_data", "client_id"),
        ("fraud_labels", "transaction_id"),
        ("mcc_codes", "mcc"),
    }
    sensitive = {
        ("users_data", "address"),
        ("users_data", "latitude"),
        ("users_data", "longitude"),
        ("cards_data", "card_number"),
        ("cards_data", "cvv"),
    }
    excluded = sensitive | {("fraud_labels", "is_fraud")}
    unavailable = sensitive | {
        ("transactions_data", "errors"),
        ("fraud_labels", "is_fraud"),
    }
    rows: list[dict[str, Any]] = []
    for item in schema:
        key = (item["source_table"], item["column_name"])
        if key == ("fraud_labels", "is_fraud"):
            role = "target"
        elif key in identifiers:
            role = "identifier"
        elif key in excluded:
            role = "excluded"
        else:
            role = "predictor_candidate"
        rows.append(
            {
                "column_name": item["column_name"],
                "source_table": item["source_table"],
                "data_type": item["data_type"],
                "description": DESCRIPTIONS.get(key, "por confirmar"),
                "role": role,
                "sensitive": "yes" if key in sensitive else "no",
                "available_at_inference": (
                    "no" if key in unavailable else "yes"
                ),
                "notes": (
                    "Definición basada en el esquema y nombre de la fuente; "
                    "validar semántica de negocio."
                ),
            }
        )
    for name, description in DERIVED_FIELDS:
        rows.append(
            {
                "column_name": name,
                "source_table": "derived",
                "data_type": "derived",
                "description": description,
                "role": "predictor_candidate",
                "sensitive": "no",
                "available_at_inference": "yes",
                "notes": "Cálculo versionado en dbo.vw_finan_features.",
            }
        )
    return rows


def profile_columns(
    connection: pyodbc.Connection, schema: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    output: list[dict[str, Any]] = []
    tables = sorted({item["source_table"] for item in schema})
    for table in tables:
        table_columns = [item for item in schema if item["source_table"] == table]
        select_parts = ["COUNT_BIG(*) AS row_count"]
        layout: list[tuple[dict[str, Any], bool, bool]] = []
        for item in table_columns:
            column = item["column_name"]
            quoted = f"[{column}]"
            is_key = (table, column) in KEY_COLUMNS
            is_money = (table, column) in MONEY_COLUMNS
            numeric = item["base_type"] in {
                "tinyint", "smallint", "int", "bigint", "decimal", "numeric",
                "float", "real", "bit",
            } or is_money
            is_date = item["base_type"] in {"date", "datetime", "datetime2"}
            select_parts.append(
                f"SUM(CASE WHEN {quoted} IS NULL THEN CONVERT(bigint,1) "
                f"ELSE CONVERT(bigint,0) END)"
            )
            if is_key:
                select_parts.append("COUNT_BIG(*)")
            else:
                select_parts.append(f"APPROX_COUNT_DISTINCT({quoted})")
            if numeric:
                expression = quoted
                if is_money:
                    expression = (
                        f"TRY_CONVERT(float, REPLACE(REPLACE({quoted}, '$', ''), ',', ''))"
                    )
                else:
                    expression = f"TRY_CONVERT(float, {quoted})"
                select_parts.extend(
                    [
                        f"MIN({expression})",
                        f"MAX({expression})",
                        f"AVG({expression})",
                        f"STDEV({expression})",
                    ]
                )
            elif is_date:
                select_parts.extend([f"MIN({quoted})", f"MAX({quoted})"])
            layout.append((item, numeric, is_date))

        query = "SELECT " + ", ".join(select_parts) + f" FROM dbo.[{table}];"
        values = list(connection.execute(query).fetchone())
        row_count = int(values[0])
        index = 1
        for item, numeric, is_date in layout:
            null_count = int(values[index] or 0)
            unique_count = int(values[index + 1] or 0)
            index += 2
            minimum = maximum = mean = standard_deviation = ""
            if numeric:
                minimum, maximum, mean, standard_deviation = values[index:index + 4]
                index += 4
            elif is_date:
                minimum, maximum = values[index:index + 2]
                index += 2
            output.append(
                {
                    "column_name": item["column_name"],
                    "source_table": table,
                    "data_type": item["data_type"],
                    "row_count": row_count,
                    "null_count": null_count,
                    "null_percentage": round(null_count * 100 / row_count, 6)
                    if row_count else 0,
                    "unique_count": unique_count,
                    "unique_count_method": "exact_primary_key" if (table, item["column_name"]) in KEY_COLUMNS else "approx_count_distinct",
                    "min_value": minimum,
                    "max_value": maximum,
                    "mean_value": mean,
                    "std_value": standard_deviation,
                    "profile_timestamp": timestamp,
                }
            )
    return output


def feature_candidates(profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["source_table"], row["column_name"]): row for row in profile
    }
    specs = [
        ("transaction_id", "transactions_data", "id", "identifier_only", "yes", "low", "Trazabilidad; se excluye del modelo."),
        ("transaction_date", "transactions_data", "date", "requires_engineering", "yes", "low", "Usar componentes temporales reproducibles."),
        ("client_id", "transactions_data", "client_id", "identifier_only", "yes", "high", "Identificador; riesgo de memorización."),
        ("card_id", "transactions_data", "card_id", "identifier_only", "yes", "high", "Identificador; riesgo de memorización."),
        ("amount", "transactions_data", "amount", "candidate", "yes", "low", "Variable transaccional disponible."),
        ("use_chip", "transactions_data", "use_chip", "candidate", "yes", "low", "Canal de transacción usado en trabajos previos."),
        ("merchant_id", "transactions_data", "merchant_id", "identifier_only", "yes", "high", "Alta cardinalidad; no usar directamente."),
        ("merchant_city", "transactions_data", "merchant_city", "requires_engineering", "yes", "medium", "Alta cardinalidad; requiere tratamiento."),
        ("merchant_state", "transactions_data", "merchant_state", "candidate", "yes", "low", "Ubicación comercial agregada."),
        ("merchant_zip", "transactions_data", "zip", "requires_review", "yes", "medium", "Granularidad geográfica y cardinalidad por revisar."),
        ("mcc", "transactions_data", "mcc", "candidate", "yes", "low", "Categoría comercial disponible."),
        ("errors", "transactions_data", "errors", "requires_review", "por confirmar", "high", "Momento de disponibilidad no documentado; posible fuga."),
        ("current_age", "users_data", "current_age", "requires_review", "yes", "medium", "Fecha de referencia no documentada; preferir age_at_transaction."),
        ("retirement_age", "users_data", "retirement_age", "candidate", "yes", "low", "Dato de perfil disponible."),
        ("birth_year", "users_data", "birth_year", "requires_engineering", "yes", "medium", "Usar solo para derivar edad; cuasi-identificador."),
        ("birth_month", "users_data", "birth_month", "requires_engineering", "yes", "medium", "Usar solo para derivar edad; cuasi-identificador."),
        ("gender", "users_data", "gender", "requires_review", "yes", "medium", "Requiere evaluación de equidad; no está en la vista oficial."),
        ("address", "users_data", "address", "excluded", "no", "high", "Dato personal directo."),
        ("latitude", "users_data", "latitude", "excluded", "no", "high", "Ubicación personal."),
        ("longitude", "users_data", "longitude", "excluded", "no", "high", "Ubicación personal."),
        ("per_capita_income", "users_data", "per_capita_income", "candidate", "yes", "medium", "Dato financiero; vigencia temporal por revisar."),
        ("yearly_income", "users_data", "yearly_income", "candidate", "yes", "medium", "Dato financiero; vigencia temporal por revisar."),
        ("total_debt", "users_data", "total_debt", "candidate", "yes", "medium", "Dato financiero; vigencia temporal por revisar."),
        ("credit_score", "users_data", "credit_score", "candidate", "yes", "medium", "Dato financiero; vigencia temporal por revisar."),
        ("num_credit_cards", "users_data", "num_credit_cards", "candidate", "yes", "low", "Dato de perfil disponible."),
        ("card_brand", "cards_data", "card_brand", "candidate", "yes", "low", "Categoría de tarjeta disponible."),
        ("card_type", "cards_data", "card_type", "candidate", "yes", "low", "Categoría de tarjeta disponible."),
        ("card_number", "cards_data", "card_number", "excluded", "no", "high", "Dato financiero sensible."),
        ("expires", "cards_data", "expires", "requires_engineering", "yes", "medium", "Usar solo para meses hasta expiración."),
        ("cvv", "cards_data", "cvv", "excluded", "no", "high", "Dato financiero sensible."),
        ("has_chip", "cards_data", "has_chip", "candidate", "yes", "low", "Capacidad de chip disponible."),
        ("num_cards_issued", "cards_data", "num_cards_issued", "candidate", "yes", "low", "Dato de cuenta disponible."),
        ("credit_limit", "cards_data", "credit_limit", "candidate", "yes", "medium", "Dato financiero disponible."),
        ("acct_open_date", "cards_data", "acct_open_date", "requires_engineering", "yes", "low", "Usar para antigüedad de cuenta."),
        ("year_pin_last_changed", "cards_data", "year_pin_last_changed", "requires_engineering", "por confirmar", "medium", "Evitar valores posteriores a la transacción."),
        ("card_on_dark_web", "cards_data", "card_on_dark_web", "requires_review", "por confirmar", "high", "Disponibilidad temporal y riesgo de proxy por confirmar."),
        ("is_fraud", "fraud_labels", "is_fraud", "excluded", "no", "high", "Variable objetivo; nunca predictor."),
        ("mcc_description", "mcc_codes", "description", "requires_review", "yes", "low", "Redundante con mcc; útil para interpretación."),
    ]
    for name, _ in DERIVED_FIELDS:
        specs.append((name, "derived", name, "candidate", "yes", "low", "Derivada reproducible en la vista oficial."))
    specs.extend(
        [
            ("frecuencia_reciente", "derived", "frecuencia_reciente", "requires_engineering", "yes", "medium", "Requiere ventana basada solo en eventos anteriores."),
            ("desviacion_comportamiento", "derived", "desviacion_comportamiento", "requires_engineering", "yes", "medium", "Requiere baseline histórico sin información futura."),
        ]
    )

    rows = []
    for feature, table, source_column, status, available, leakage, reason in specs:
        profile_row = lookup.get((table, source_column), {})
        data_type = profile_row.get("data_type", "derived")
        rows.append(
            {
                "feature": feature,
                "source_table": table,
                "data_type": data_type,
                "candidate_status": status,
                "available_at_inference": available,
                "leakage_risk": leakage,
                "cardinality": profile_row.get("unique_count", "por confirmar"),
                "missing_percentage": profile_row.get("null_percentage", "por confirmar"),
                "reason": reason,
            }
        )
    return rows


def create_mcc_csv(connection: pyodbc.Connection, path: Path) -> int:
    rows = [
        {"mcc": int(code), "description": str(description).strip()}
        for code, description in connection.execute(
            "SELECT mcc, description FROM dbo.mcc_codes ORDER BY mcc"
        ).fetchall()
    ]
    write_csv(path, ["mcc", "description"], rows)
    return len(rows)


def create_sample(
    connection: pyodbc.Connection,
    path: Path,
    snapshot_version: str,
    seed: int,
) -> int:
    class_rows = connection.execute(
        """
        SELECT d.is_fraud, COUNT_BIG(*)
        FROM dbo.finan_split_assignment AS a
        INNER JOIN dbo.vw_dataset_maestro AS d
            ON d.transaction_id = a.transaction_id
        WHERE a.snapshot_version = ? AND a.split = 'train'
        GROUP BY d.is_fraud;
        """,
        snapshot_version,
    ).fetchall()
    counts = {int(label): int(count) for label, count in class_rows}
    total = sum(counts.values())
    if total != 1_050_000 or counts.get(1, 0) <= 0:
        raise RuntimeError("El split train no está listo para generar la muestra.")
    fraud_quota = int(
        (Decimal(10_000) * Decimal(counts[1]) / Decimal(total)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    nonfraud_quota = 10_000 - fraud_quota

    selected_columns = [
        "transaction_id", "transaction_date", "transaction_hour", "day_of_week",
        "is_weekend", "transaction_month", "amount", "use_chip",
        "merchant_state", "mcc", "age_at_transaction", "retirement_age",
        "per_capita_income", "yearly_income", "total_debt", "credit_score",
        "num_credit_cards", "card_brand", "card_type", "has_chip",
        "num_cards_issued", "credit_limit", "account_open_month",
        "account_open_year", "years_since_pin_change", "card_on_dark_web",
        "mcc_description", "amount_to_credit_limit", "amount_to_yearly_income",
        "card_account_age_years", "months_to_card_expiration", "is_fraud",
    ]
    select_sql = ", ".join(f"d.[{name}]" for name in selected_columns)
    output_sql = ", ".join(f"[{name}]" for name in selected_columns)
    query = f"""
        WITH ranked AS
        (
            SELECT {select_sql},
                   ROW_NUMBER() OVER
                   (
                       PARTITION BY d.is_fraud
                       ORDER BY
                           (CONVERT(bigint, CHECKSUM(
                               d.transaction_id, ?, ?
                           )) & 2147483647),
                           d.transaction_id
                   ) AS sample_rank
            FROM dbo.finan_split_assignment AS a
            INNER JOIN dbo.vw_dataset_maestro AS d
                ON d.transaction_id = a.transaction_id
            WHERE a.snapshot_version = ? AND a.split = 'train'
        )
        SELECT {output_sql}, 'train' AS split
        FROM ranked
        WHERE (is_fraud = 0 AND sample_rank <= ?)
           OR (is_fraud = 1 AND sample_rank <= ?)
        ORDER BY transaction_id;
    """
    cursor = connection.cursor()
    cursor.execute(
        query,
        seed + 10_000,
        snapshot_version,
        snapshot_version,
        nonfraud_quota,
        fraud_quota,
    )
    headers = [column[0] for column in cursor.description]
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        while True:
            rows = cursor.fetchmany(5_000)
            if not rows:
                break
            writer.writerows(rows)
            count += len(rows)
    cursor.close()
    if count != 10_000:
        raise RuntimeError(f"La muestra generó {count} filas, no 10.000.")
    return count


def main() -> int:
    args = parse_args()
    try:
        source_dir = args.source_dir.resolve()
        missing = [name for name in SOURCE_FILES if not (source_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                "Faltan fuentes: " + ", ".join(sorted(missing))
            )
        args.reference_dir.mkdir(parents=True, exist_ok=True)
        args.sample_dir.mkdir(parents=True, exist_ok=True)

        connection = connect(args)
        try:
            schema = schema_rows(connection)
            dictionary_rows = data_dictionary(schema)
            profile_rows = profile_columns(connection, schema)
            candidate_rows = feature_candidates(profile_rows)

            write_csv(
                args.reference_dir / "data_dictionary.csv",
                [
                    "column_name", "source_table", "data_type", "description",
                    "role", "sensitive", "available_at_inference", "notes",
                ],
                dictionary_rows,
            )
            write_csv(
                args.reference_dir / "column_profile.csv",
                [
                    "column_name", "source_table", "data_type", "row_count",
                    "null_count", "null_percentage", "unique_count",
                    "unique_count_method", "min_value", "max_value", "mean_value",
                    "std_value", "profile_timestamp",
                ],
                profile_rows,
            )
            write_csv(
                args.reference_dir / "feature_candidates.csv",
                [
                    "feature", "source_table", "data_type", "candidate_status",
                    "available_at_inference", "leakage_risk", "cardinality",
                    "missing_percentage", "reason",
                ],
                candidate_rows,
            )
            mcc_count = create_mcc_csv(
                connection, args.reference_dir / "mcc_codes.csv"
            )
            sample_count = create_sample(
                connection,
                args.sample_dir / "finan_sample_10000.csv",
                args.snapshot_version,
                args.seed,
            )

            table_counts = {
                table: int(
                    connection.execute(
                        f"SELECT COUNT_BIG(*) FROM dbo.[{table}]"
                    ).fetchone()[0]
                )
                for table in FILE_TO_TABLE.values()
            }
            linked_total, frauds = connection.execute(
                """
                SELECT COUNT_BIG(*), SUM(CONVERT(bigint, is_fraud))
                FROM dbo.vw_dataset_maestro;
                """
            ).fetchone()
            split_counts = {
                str(name): int(count)
                for name, count in connection.execute(
                    """
                    SELECT split, COUNT_BIG(*)
                    FROM dbo.finan_split_assignment
                    WHERE snapshot_version = ?
                    GROUP BY split;
                    """,
                    args.snapshot_version,
                ).fetchall()
            }
            current_snapshot_hash = snapshot_hash(
                connection, args.snapshot_version
            )
            sql_version = str(
                connection.execute(
                    "SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(50))"
                ).fetchone()[0]
            )
        finally:
            connection.close()

        source_files = []
        for name in SOURCE_FILES:
            path = source_dir / name
            rows = source_row_count(path)
            table = FILE_TO_TABLE[name]
            source_files.append(
                {
                    "name": name,
                    "size_bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                    "row_count": rows,
                    "loaded_table": table,
                    "loaded_row_count": table_counts[table],
                }
            )

        manifest = {
            "dataset_name": "Transactions Fraud Datasets",
            "public_source": "https://www.kaggle.com/datasets/computingvictor/transactions-fraud-datasets/data",
            "source_files": source_files,
            "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "database": {
                "logical_name": "FraudeDB",
                "sql_server_version": sql_version,
                "transactions_total": table_counts["transactions_data"],
                "linked_labeled_transactions": int(linked_total),
                "frauds": int(frauds),
                "reconstruction_note": (
                    "Reconstrucción funcional desde fuentes públicas; no es una copia "
                    "binaria del respaldo original incompleto."
                ),
            },
            "snapshot": {
                "version": args.snapshot_version,
                "size": 1_500_000,
                "seed": args.seed,
                "split_counts": split_counts,
                "hash_sha256": current_snapshot_hash,
                "selection_method": (
                    "selección estratificada por hash CHECKSUM determinista y "
                    "asignación persistida por transaction_id"
                ),
            },
            "small_sample": {
                "name": "finan_sample_10000.csv",
                "row_count": sample_count,
                "source_split": "train",
                "purpose": "smoke tests y demostraciones; no evaluación representativa",
                "sanitization": (
                    "excluye número de tarjeta, CVV, domicilio, coordenadas e "
                    "identificadores de cliente, tarjeta y comercio"
                ),
            },
            "software": {
                "python_version": platform.python_version(),
                "pyodbc_version": pyodbc.version,
                "sql_driver": args.driver,
                "sql_driver_version": args.driver_version,
            },
            "mcc_rows": mcc_count,
            "reproducibility_notes": [
                "El dataset completo, la base, el respaldo y el snapshot de 1,5M no se versionan.",
                "El conjunto test queda reservado y no fue utilizado para selección o modelado.",
                "Las variables candidatas no constituyen una selección predictiva definitiva.",
            ],
        }
        (args.reference_dir / "source_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print("INSPECCIÓN COMPLETADA")
        print(f"Diccionario: {len(dictionary_rows)} filas")
        print(f"Perfil: {len(profile_rows)} filas")
        print(f"Variables candidatas: {len(candidate_rows)} filas")
        print(f"MCC: {mcc_count} filas")
        print(f"Muestra pequeña: {sample_count} filas")
        print(f"Snapshot SHA-256: {current_snapshot_hash}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
