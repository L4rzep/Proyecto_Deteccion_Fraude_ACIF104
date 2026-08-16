"""Construye y persiste el snapshot oficial FINAN de forma determinista."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

import pyodbc


DEFAULT_VERSION = "finan-1500k-seed42-v1"
SAMPLE_SIZE = 1_500_000
TRAIN_SIZE = 1_050_000
VALIDATION_SIZE = 225_000
TEST_SIZE = 225_000


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
    parser.add_argument("--snapshot-version", default=DEFAULT_VERSION)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--query-timeout", type=int, default=0)
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=False)


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def class_quotas(total: int, frauds: int) -> dict[str, dict[int, int]]:
    sample_fraud = round_half_up(
        Decimal(SAMPLE_SIZE) * Decimal(frauds) / Decimal(total)
    )
    sample_nonfraud = SAMPLE_SIZE - sample_fraud

    train_fraud = round_half_up(Decimal(sample_fraud) * Decimal("0.70"))
    validation_fraud = round_half_up(
        Decimal(sample_fraud) * Decimal("0.15")
    )
    test_fraud = sample_fraud - train_fraud - validation_fraud

    return {
        "sample": {0: sample_nonfraud, 1: sample_fraud},
        "train": {0: TRAIN_SIZE - train_fraud, 1: train_fraud},
        "validation": {
            0: VALIDATION_SIZE - validation_fraud,
            1: validation_fraud,
        },
        "test": {0: TEST_SIZE - test_fraud, 1: test_fraud},
    }


def snapshot_hash(
    connection: pyodbc.Connection, snapshot_version: str
) -> str:
    digest = hashlib.sha256()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT transaction_id, split, seed
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?
        ORDER BY transaction_id;
        """,
        snapshot_version,
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


def existing_summary(
    connection: pyodbc.Connection, snapshot_version: str
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT split, COUNT_BIG(*)
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?
        GROUP BY split;
        """,
        snapshot_version,
    ).fetchall()
    return {str(split_name): int(count) for split_name, count in rows}


def validate_existing(
    connection: pyodbc.Connection,
    snapshot_version: str,
    seed: int,
) -> tuple[dict[str, int], str] | None:
    summary = existing_summary(connection, snapshot_version)
    if not summary:
        return None
    expected = {
        "train": TRAIN_SIZE,
        "validation": VALIDATION_SIZE,
        "test": TEST_SIZE,
    }
    if summary != expected:
        raise RuntimeError(
            f"La versión {snapshot_version!r} ya existe incompleta: {summary}"
        )
    seed_row = connection.execute(
        """
        SELECT MIN(seed), MAX(seed)
        FROM dbo.finan_split_assignment
        WHERE snapshot_version = ?;
        """,
        snapshot_version,
    ).fetchone()
    if int(seed_row[0]) != seed or int(seed_row[1]) != seed:
        raise RuntimeError("El snapshot existente utiliza una semilla diferente.")
    return summary, snapshot_hash(connection, snapshot_version)


def insert_snapshot(
    connection: pyodbc.Connection,
    snapshot_version: str,
    seed: int,
    quotas: dict[str, dict[int, int]],
    timeout: int,
) -> None:
    bucket_mod = 4
    if timeout > 0:
        connection.timeout = timeout
    cursor = connection.cursor()

    candidate_rows = cursor.execute(
        """
        SELECT is_fraud, COUNT_BIG(*)
        FROM dbo.vw_dataset_maestro
        WHERE
            (CONVERT(bigint, CHECKSUM(transaction_id, ?, ?)) & 2147483647)
            % ? = 0
        GROUP BY is_fraud;
        """,
        seed,
        snapshot_version,
        bucket_mod,
    ).fetchall()
    candidates = {int(label): int(count) for label, count in candidate_rows}
    for label in (0, 1):
        if candidates.get(label, 0) < quotas["sample"][label]:
            raise RuntimeError(
                "El subconjunto determinista no contiene suficientes filas "
                f"para la clase {label}."
            )

    statement = """
    DECLARE @snapshot_version nvarchar(100) = ?;
    DECLARE @seed int = ?;
    DECLARE @bucket_mod int = ?;
    DECLARE @sample_nonfraud bigint = ?;
    DECLARE @sample_fraud bigint = ?;
    DECLARE @train_nonfraud bigint = ?;
    DECLARE @train_fraud bigint = ?;
    DECLARE @validation_nonfraud bigint = ?;
    DECLARE @validation_fraud bigint = ?;

    ;WITH candidates AS
    (
        SELECT
            transaction_id,
            is_fraud,
            ROW_NUMBER() OVER
            (
                PARTITION BY is_fraud
                ORDER BY
                    (CONVERT(bigint, CHECKSUM(
                        transaction_id, @seed, @snapshot_version
                    )) & 2147483647),
                    transaction_id
            ) AS sample_rank
        FROM dbo.vw_dataset_maestro
        WHERE
            (CONVERT(bigint, CHECKSUM(
                transaction_id, @seed, @snapshot_version
            )) & 2147483647) % @bucket_mod = 0
    ),
    selected AS
    (
        SELECT transaction_id, is_fraud
        FROM candidates
        WHERE
            (is_fraud = 0 AND sample_rank <= @sample_nonfraud)
            OR (is_fraud = 1 AND sample_rank <= @sample_fraud)
    ),
    split_ranked AS
    (
        SELECT
            transaction_id,
            is_fraud,
            ROW_NUMBER() OVER
            (
                PARTITION BY is_fraud
                ORDER BY
                    (CONVERT(bigint, CHECKSUM(
                        transaction_id, @seed + 1, @snapshot_version
                    )) & 2147483647),
                    transaction_id
            ) AS split_rank
        FROM selected
    )
    INSERT INTO dbo.finan_split_assignment
    (
        transaction_id, snapshot_version, split, seed, created_at
    )
    SELECT
        transaction_id,
        @snapshot_version,
        CASE
            WHEN is_fraud = 0 AND split_rank <= @train_nonfraud
                THEN 'train'
            WHEN is_fraud = 1 AND split_rank <= @train_fraud
                THEN 'train'
            WHEN is_fraud = 0
                 AND split_rank <= @train_nonfraud + @validation_nonfraud
                THEN 'validation'
            WHEN is_fraud = 1
                 AND split_rank <= @train_fraud + @validation_fraud
                THEN 'validation'
            ELSE 'test'
        END,
        @seed,
        SYSUTCDATETIME()
    FROM split_ranked;
    """
    cursor.execute(
        statement,
        snapshot_version,
        seed,
        bucket_mod,
        quotas["sample"][0],
        quotas["sample"][1],
        quotas["train"][0],
        quotas["train"][1],
        quotas["validation"][0],
        quotas["validation"][1],
    )
    connection.commit()
    cursor.close()


def main() -> int:
    args = parse_args()
    if not args.snapshot_version.strip():
        print("ERROR: --snapshot-version no puede estar vacío.", file=sys.stderr)
        return 2
    try:
        connection = connect(args)
        try:
            existing = validate_existing(
                connection, args.snapshot_version, args.seed
            )
            if existing:
                summary, current_hash = existing
                print("Snapshot ya existente y válido; no se duplicaron filas.")
            else:
                total, frauds = connection.execute(
                    """
                    SELECT COUNT_BIG(*),
                           SUM(CONVERT(bigint, is_fraud))
                    FROM dbo.vw_dataset_maestro;
                    """
                ).fetchone()
                total, frauds = int(total), int(frauds)
                if total < SAMPLE_SIZE or frauds <= 0:
                    raise RuntimeError(
                        "La vista etiquetada no contiene datos suficientes."
                    )
                quotas = class_quotas(total, frauds)
                insert_snapshot(
                    connection,
                    args.snapshot_version,
                    args.seed,
                    quotas,
                    args.query_timeout,
                )
                existing = validate_existing(
                    connection, args.snapshot_version, args.seed
                )
                if existing is None:
                    raise RuntimeError("El snapshot no quedó persistido.")
                summary, current_hash = existing

            class_rows = connection.execute(
                """
                SELECT a.split, d.is_fraud, COUNT_BIG(*)
                FROM dbo.finan_split_assignment AS a
                INNER JOIN dbo.vw_dataset_maestro AS d
                    ON d.transaction_id = a.transaction_id
                WHERE a.snapshot_version = ?
                GROUP BY a.split, d.is_fraud
                ORDER BY a.split, d.is_fraud;
                """,
                args.snapshot_version,
            ).fetchall()
        finally:
            connection.close()

        print("\nSNAPSHOT OFICIAL FINAN")
        print(f"Versión: {args.snapshot_version}")
        print(f"Semilla: {args.seed}")
        for split_name in ("train", "validation", "test"):
            print(f"{split_name}: {summary[split_name]:,}")
        for split_name, label, count in class_rows:
            print(f"{split_name}/is_fraud={int(label)}: {int(count):,}")
        print(f"SHA-256: {current_hash}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
