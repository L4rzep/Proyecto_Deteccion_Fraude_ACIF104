"""Carga por lotes las cinco fuentes públicas en las tablas de FraudeDB.

No crea ni elimina la base. Requiere ejecutar primero
``src/data/sql/01_create_source_tables.sql`` y omite cualquier tabla que ya
contenga registros.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import pyodbc


CSV_SOURCES = {
    "users_data": (
        "users_data.csv",
        [
            "id", "current_age", "retirement_age", "birth_year",
            "birth_month", "gender", "address", "latitude", "longitude",
            "per_capita_income", "yearly_income", "total_debt",
            "credit_score", "num_credit_cards",
        ],
    ),
    "cards_data": (
        "cards_data.csv",
        [
            "id", "client_id", "card_brand", "card_type", "card_number",
            "expires", "cvv", "has_chip", "num_cards_issued",
            "credit_limit", "acct_open_date", "year_pin_last_changed",
            "card_on_dark_web",
        ],
    ),
    "transactions_data": (
        "transactions_data.csv",
        [
            "id", "date", "client_id", "card_id", "amount", "use_chip",
            "merchant_id", "merchant_city", "merchant_state", "zip", "mcc",
            "errors",
        ],
    ),
}

JSON_SOURCES = {
    "fraud_labels": "train_fraud_labels.json",
    "mcc_codes": "mcc_codes.json",
}

LABEL_PAIR = re.compile(r'"(?P<id>\d+)"\s*:\s*"(?P<label>Yes|No)"')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=os.getenv("FINAN_SOURCE_DIR"),
        required=os.getenv("FINAN_SOURCE_DIR") is None,
        help="Carpeta que contiene los cinco archivos fuente.",
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
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument(
        "--only",
        choices=[*CSV_SOURCES, *JSON_SOURCES],
        nargs="+",
        help="Carga únicamente las tablas indicadas.",
    )
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=False)


def clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def table_count(connection: pyodbc.Connection, table: str) -> int:
    row = connection.execute(
        f"SELECT COUNT_BIG(*) FROM dbo.[{table}]"
    ).fetchone()
    return int(row[0])


def insert_batches(
    connection: pyodbc.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    batch_size: int,
) -> int:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(f"[{column}]" for column in columns)
    statement = (
        f"INSERT INTO dbo.[{table}] ({column_sql}) VALUES ({placeholders})"
    )
    cursor = connection.cursor()
    cursor.fast_executemany = True
    batch: list[Sequence[object]] = []
    inserted = 0

    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            cursor.executemany(statement, batch)
            connection.commit()
            inserted += len(batch)
            print(f"  {table}: {inserted:,} filas", flush=True)
            batch.clear()

    if batch:
        cursor.executemany(statement, batch)
        connection.commit()
        inserted += len(batch)
        print(f"  {table}: {inserted:,} filas", flush=True)

    cursor.close()
    return inserted


def iter_csv_rows(path: Path, columns: Sequence[str]) -> Iterator[list[object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(columns):
            raise ValueError(
                f"Encabezado inesperado en {path.name}: {reader.fieldnames}"
            )
        for source_row in reader:
            yield [clean_value(source_row[column]) for column in columns]


def iter_label_rows(path: Path) -> Iterator[tuple[int, int]]:
    """Lee el JSON de 159 MB sin cargarlo completo en memoria."""
    carry = ""
    with path.open("r", encoding="utf-8") as stream:
        while True:
            chunk = stream.read(1_048_576)
            if not chunk:
                break
            parts = (carry + chunk).split(",")
            carry = parts.pop()
            for part in parts:
                match = LABEL_PAIR.search(part)
                if match:
                    yield (
                        int(match.group("id")),
                        1 if match.group("label") == "Yes" else 0,
                    )
        match = LABEL_PAIR.search(carry)
        if match:
            yield (
                int(match.group("id")),
                1 if match.group("label") == "Yes" else 0,
            )


def iter_mcc_rows(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8") as stream:
        content = json.load(stream)
    for code, description in sorted(content.items(), key=lambda item: int(item[0])):
        yield int(code), str(description).strip()


def require_sources(source_dir: Path) -> None:
    expected = [name for name, _ in CSV_SOURCES.values()] + list(
        JSON_SOURCES.values()
    )
    missing = [name for name in expected if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos fuente: " + ", ".join(sorted(missing))
        )


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        print("ERROR: --batch-size debe ser positivo.", file=sys.stderr)
        return 2

    source_dir = args.source_dir.resolve()
    selected = set(args.only or [*CSV_SOURCES, *JSON_SOURCES])

    try:
        require_sources(source_dir)
        connection = connect(args)
        summary: dict[str, str] = {}
        try:
            for table, (filename, columns) in CSV_SOURCES.items():
                if table not in selected:
                    continue
                existing = table_count(connection, table)
                if existing:
                    summary[table] = f"omitida; ya contiene {existing:,} filas"
                    continue
                inserted = insert_batches(
                    connection,
                    table,
                    columns,
                    iter_csv_rows(source_dir / filename, columns),
                    args.batch_size,
                )
                summary[table] = f"{inserted:,} filas cargadas"

            if "fraud_labels" in selected:
                existing = table_count(connection, "fraud_labels")
                if existing:
                    summary["fraud_labels"] = (
                        f"omitida; ya contiene {existing:,} filas"
                    )
                else:
                    inserted = insert_batches(
                        connection,
                        "fraud_labels",
                        ["transaction_id", "is_fraud"],
                        iter_label_rows(source_dir / JSON_SOURCES["fraud_labels"]),
                        args.batch_size,
                    )
                    summary["fraud_labels"] = f"{inserted:,} filas cargadas"

            if "mcc_codes" in selected:
                existing = table_count(connection, "mcc_codes")
                if existing:
                    summary["mcc_codes"] = (
                        f"omitida; ya contiene {existing:,} filas"
                    )
                else:
                    inserted = insert_batches(
                        connection,
                        "mcc_codes",
                        ["mcc", "description"],
                        iter_mcc_rows(source_dir / JSON_SOURCES["mcc_codes"]),
                        args.batch_size,
                    )
                    summary["mcc_codes"] = f"{inserted:,} filas cargadas"
        finally:
            connection.close()

        print("\nRESUMEN DE CARGA")
        for table in [*CSV_SOURCES, *JSON_SOURCES]:
            if table in summary:
                print(f"- {table}: {summary[table]}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
