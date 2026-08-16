"""Valida integridad, vistas, snapshot, manifiesto y muestra FINAN."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pyodbc


EXPECTED_SPLITS = {"train": 1_050_000, "validation": 225_000, "test": 225_000}
SENSITIVE_COLUMNS = {
    "card_number",
    "cvv",
    "address",
    "latitude",
    "longitude",
    "expires",
}


def parse_args() -> argparse.Namespace:
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
    parser.add_argument(
        "--snapshot-version", default="finan-1500k-seed42-v1"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/reference/source_manifest.json"),
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("data/sample/finan_sample_10000.csv"),
    )
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=True)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


class Validation:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def check(self, condition: bool, label: str, detail: Any = "") -> None:
        suffix = f" ({detail})" if detail != "" else ""
        if condition:
            print(f"[OK] {label}{suffix}")
        else:
            message = f"{label}{suffix}"
            self.failures.append(message)
            print(f"[FALLA] {message}")

    def warn(self, label: str, detail: Any = "") -> None:
        suffix = f" ({detail})" if detail != "" else ""
        message = f"{label}{suffix}"
        self.warnings.append(message)
        print(f"[AVISO] {message}")


def scalar(connection: pyodbc.Connection, statement: str, *params: Any) -> Any:
    return connection.execute(statement, *params).fetchone()[0]


def columns(connection: pyodbc.Connection, object_name: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT c.name
        FROM sys.columns AS c
        WHERE c.object_id = OBJECT_ID(?)
        ORDER BY c.column_id;
        """,
        object_name,
    ).fetchall()
    return [str(row[0]) for row in rows]


def validate_database(
    connection: pyodbc.Connection, args: argparse.Namespace, result: Validation
) -> dict[str, int | str]:
    required_tables = [
        "transactions_data",
        "users_data",
        "cards_data",
        "fraud_labels",
        "mcc_codes",
        "finan_split_assignment",
        "Resultados_Fraude_FINAN",
    ]
    for table in required_tables:
        exists = int(
            scalar(
                connection,
                "SELECT COUNT(*) FROM sys.tables WHERE object_id = OBJECT_ID(?)",
                f"dbo.{table}",
            )
        )
        result.check(exists == 1, f"Existe dbo.{table}")

    counts: dict[str, int] = {}
    for table in [
        "transactions_data",
        "users_data",
        "cards_data",
        "fraud_labels",
        "mcc_codes",
    ]:
        counts[table] = int(
            scalar(connection, f"SELECT COUNT_BIG(*) FROM dbo.[{table}]")
        )
        result.check(counts[table] > 0, f"{table} contiene datos", counts[table])

    key_checks = {
        "transactions_data.id": ("transactions_data", "id"),
        "users_data.id": ("users_data", "id"),
        "cards_data.id": ("cards_data", "id"),
        "fraud_labels.transaction_id": ("fraud_labels", "transaction_id"),
        "mcc_codes.mcc": ("mcc_codes", "mcc"),
    }
    for label, (table, key) in key_checks.items():
        duplicate_groups = int(
            scalar(
                connection,
                f"""
                SELECT COUNT_BIG(*) FROM
                (
                    SELECT [{key}]
                    FROM dbo.[{table}]
                    GROUP BY [{key}]
                    HAVING COUNT_BIG(*) > 1
                ) AS duplicates;
                """,
            )
        )
        result.check(duplicate_groups == 0, f"Unicidad de {label}")

    parse_errors = int(
        scalar(
            connection,
            """
            SELECT COUNT_BIG(*)
            FROM dbo.transactions_data
            WHERE amount IS NOT NULL
              AND TRY_CONVERT(decimal(18,2),
                    REPLACE(REPLACE(amount, '$', ''), ',', '')) IS NULL;
            """,
        )
    )
    result.check(parse_errors == 0, "Montos convertibles", parse_errors)

    invalid_users = int(
        scalar(
            connection,
            """
            SELECT COUNT_BIG(*) FROM dbo.users_data
            WHERE (birth_month IS NOT NULL AND birth_month NOT BETWEEN 1 AND 12)
               OR (credit_score IS NOT NULL AND credit_score NOT BETWEEN 300 AND 850)
               OR (current_age IS NOT NULL AND current_age NOT BETWEEN 0 AND 120);
            """,
        )
    )
    result.check(invalid_users == 0, "Valores de usuario dentro de rangos", invalid_users)

    join_row = connection.execute(
        """
        SELECT
            SUM(CASE WHEN f.transaction_id IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN u.id IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN c.id IS NULL OR c.client_id <> t.client_id THEN 1 ELSE 0 END)
        FROM dbo.transactions_data AS t
        LEFT JOIN dbo.fraud_labels AS f ON f.transaction_id = t.id
        LEFT JOIN dbo.users_data AS u ON u.id = t.client_id
        LEFT JOIN dbo.cards_data AS c ON c.id = t.card_id;
        """
    ).fetchone()
    without_label, without_user, without_card = map(int, join_row)
    result.warn("Transacciones sin etiqueta", without_label)
    result.check(without_user == 0, "Integridad transacción-usuario", without_user)
    result.check(without_card == 0, "Integridad transacción-tarjeta", without_card)

    labels_without_transaction = int(
        scalar(
            connection,
            """
            SELECT COUNT_BIG(*)
            FROM dbo.fraud_labels AS f
            LEFT JOIN dbo.transactions_data AS t ON t.id = f.transaction_id
            WHERE t.id IS NULL;
            """,
        )
    )
    result.check(
        labels_without_transaction == 0,
        "Etiquetas vinculadas a una transacción",
        labels_without_transaction,
    )

    feature_columns = columns(connection, "dbo.vw_finan_features")
    dataset_columns = columns(connection, "dbo.vw_dataset_maestro")
    result.check(bool(feature_columns), "Existe dbo.vw_finan_features")
    result.check(bool(dataset_columns), "Existe dbo.vw_dataset_maestro")
    result.check("is_fraud" not in feature_columns, "Inferencia sin is_fraud")
    result.check("is_fraud" in dataset_columns, "Entrenamiento con is_fraud")
    result.check(
        feature_columns == [name for name in dataset_columns if name != "is_fraud"],
        "Variables consistentes entre ambas vistas",
    )
    exposed = sorted(SENSITIVE_COLUMNS.intersection(feature_columns))
    result.check(not exposed, "Vista de inferencia sin campos sensibles", exposed)

    split_rows = connection.execute(
        """
        SELECT split, COUNT_BIG(*)
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?
        GROUP BY split;
        """,
        args.snapshot_version,
    ).fetchall()
    split_counts = {str(name): int(count) for name, count in split_rows}
    result.check(
        split_counts == EXPECTED_SPLITS,
        "Conteos exactos 70/15/15",
        split_counts,
    )
    result.check(
        sum(split_counts.values()) == 1_500_000,
        "Snapshot de 1.500.000 filas",
        sum(split_counts.values()),
    )

    duplicate_snapshot = int(
        scalar(
            connection,
            """
            SELECT COUNT_BIG(*) FROM
            (
                SELECT transaction_id
                FROM dbo.finan_split_assignment
                WHERE snapshot_version = ?
                GROUP BY transaction_id
                HAVING COUNT_BIG(*) > 1
            ) AS duplicates;
            """,
            args.snapshot_version,
        )
    )
    result.check(
        duplicate_snapshot == 0,
        "Snapshot sin IDs duplicados ni solapamientos",
    )
    seed_range = connection.execute(
        """
        SELECT MIN(seed), MAX(seed)
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?;
        """,
        args.snapshot_version,
    ).fetchone()
    result.check(
        seed_range[0] == args.seed and seed_range[1] == args.seed,
        "Semilla persistida",
        seed_range,
    )

    distribution_rows = connection.execute(
        """
        SELECT a.split, COUNT_BIG(*) AS total,
               SUM(CONVERT(bigint, d.is_fraud)) AS frauds
        FROM dbo.finan_split_assignment AS a
        INNER JOIN dbo.vw_dataset_maestro AS d
            ON d.transaction_id = a.transaction_id
        WHERE a.snapshot_version = ?
        GROUP BY a.split;
        """,
        args.snapshot_version,
    ).fetchall()
    full_total, full_frauds = connection.execute(
        """
        SELECT COUNT_BIG(*), SUM(CONVERT(bigint, is_fraud))
        FROM dbo.vw_dataset_maestro;
        """
    ).fetchone()
    full_rate = int(full_frauds) / int(full_total)
    for split_name, split_total, split_frauds in distribution_rows:
        split_rate = int(split_frauds) / int(split_total)
        result.check(
            abs(split_rate - full_rate) <= 0.0001,
            f"Estratificación conservada en {split_name}",
            f"{split_rate:.6%}",
        )

    current_hash = snapshot_hash(connection, args.snapshot_version)
    return {
        "transactions_total": counts["transactions_data"],
        "linked_total": int(full_total),
        "frauds": int(full_frauds),
        "snapshot_hash": current_hash,
    }


def validate_artifacts(
    args: argparse.Namespace,
    database_summary: dict[str, int | str],
    result: Validation,
) -> int:
    sample_rows = 0
    if args.sample.is_file():
        with args.sample.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            for _ in reader:
                sample_rows += 1
        result.check(sample_rows == 10_000, "Muestra pequeña de 10.000 filas", sample_rows)
        exposed = sorted(SENSITIVE_COLUMNS.intersection(header))
        result.check(not exposed, "Muestra pequeña sanitizada", exposed)
        result.check("transaction_id" in header, "Muestra conserva transaction_id")
    else:
        result.check(False, "Existe la muestra pequeña", args.sample)

    if not args.manifest.is_file():
        result.check(False, "Existe source_manifest.json", args.manifest)
        return sample_rows

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    snapshot = manifest.get("snapshot", {})
    result.check(
        snapshot.get("hash_sha256") == database_summary["snapshot_hash"],
        "Hash del snapshot coincide con el manifiesto",
    )
    result.check(snapshot.get("seed") == args.seed, "Semilla del manifiesto")
    result.check(
        snapshot.get("split_counts") == EXPECTED_SPLITS,
        "Conteos del manifiesto",
    )

    if args.source_dir:
        manifest_files = {
            item.get("name"): item for item in manifest.get("source_files", [])
        }
        for name, item in manifest_files.items():
            source_path = args.source_dir / name
            result.check(source_path.is_file(), f"Existe fuente {name}")
            if source_path.is_file():
                current_hash = hash_file(source_path)
                result.check(
                    current_hash == item.get("sha256"),
                    f"SHA-256 de {name}",
                )
    return sample_rows


def main() -> int:
    args = parse_args()
    result = Validation()
    try:
        connection = connect(args)
        try:
            database_summary = validate_database(connection, args, result)
        finally:
            connection.close()
        sample_rows = validate_artifacts(args, database_summary, result)

        print("\nRESUMEN REAL")
        print(f"Transacciones totales: {database_summary['transactions_total']:,}")
        print(f"Transacciones vinculadas: {database_summary['linked_total']:,}")
        print(f"Fraudes: {database_summary['frauds']:,}")
        print(f"Snapshot: {sum(EXPECTED_SPLITS.values()):,}")
        for name, count in EXPECTED_SPLITS.items():
            print(f"{name}: {count:,}")
        print(f"Hash snapshot: {database_summary['snapshot_hash']}")
        print(f"Filas muestra pequeña: {sample_rows:,}")

        if result.warnings:
            print(f"Avisos no críticos: {len(result.warnings)}")
        if result.failures:
            print("\nVALIDACIÓN RECHAZADA")
            for failure in result.failures:
                print(f"- {failure}")
            return 1
        print("\nVALIDACIÓN APROBADA")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("VALIDACIÓN RECHAZADA")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
