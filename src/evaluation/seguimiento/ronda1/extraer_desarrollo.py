"""Exportación de lectura: reproduce la partición S9 y excluye su test.

Ejecutar en el equipo que contiene FraudeDB. No entrena ni cambia la base.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

NUMERIC = [
    "amount", "age_at_transaction", "num_credit_cards", "num_cards_issued",
    "card_account_age_years", "months_to_card_expiration", "years_since_pin_change",
    "credit_limit", "per_capita_income", "yearly_income", "total_debt",
    "credit_score", "amount_to_credit_limit", "amount_to_yearly_income",
]
CATEGORICAL = [
    "transaction_hour", "day_of_week", "transaction_month", "use_chip", "mcc",
    "card_brand", "card_type", "has_chip",
]
COLUMNS = ["transaction_id", "transaction_date", *NUMERIC, *CATEGORICAL, "is_fraud"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def original_splits(target):
    indexes = np.arange(len(target))
    train, temporary = train_test_split(
        indexes, test_size=0.30, random_state=42, stratify=target
    )
    validation, test = train_test_split(
        temporary, test_size=0.50, random_state=42, stratify=target.iloc[temporary]
    )
    return train, validation, test


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=os.getenv("FINAN_SQL_SERVER", r"(localdb)\MSSQLLocalDB"))
    parser.add_argument("--database", default=os.getenv("FINAN_SQL_DATABASE", "FraudeDB"))
    parser.add_argument("--driver", default=os.getenv("FINAN_SQL_DRIVER", "ODBC Driver 17 for SQL Server"))
    parser.add_argument("--output", type=Path, default=Path("finan_desarrollo.csv.gz"))
    args = parser.parse_args()
    import pyodbc

    output = args.output.resolve()
    manifest = Path(str(output) + ".json")
    if output.exists() or manifest.exists():
        raise ValueError("La salida ya existe. Elija otro --output para conservarla.")
    if importlib.metadata.version("scikit-learn") != "1.9.0":
        raise RuntimeError("Use scikit-learn 1.9.0, la versión registrada en la partición S9.")
    connection_string = os.getenv("FINAN_ODBC_CONNECTION") or (
        f"DRIVER={{{args.driver}}};SERVER={args.server};DATABASE={args.database};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )
    query = (
        "SELECT " + ", ".join(f"[{c}]" for c in COLUMNS)
        + " FROM dbo.vw_dataset_maestro"
        + " WHERE (CHECKSUM(transaction_id, 42) & 2147483647) % 9 = 0"
        + " ORDER BY transaction_id"
    )
    connection = pyodbc.connect(connection_string, autocommit=True, timeout=30)
    connection.timeout = 0
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        columns = [item[0] for item in cursor.description]
        blocks, count = [], 0
        while True:
            rows = cursor.fetchmany(50_000)
            if not rows:
                break
            blocks.append(pd.DataFrame.from_records(rows, columns=columns))
            count += len(rows)
            print(f"Leídas {count:,} filas", flush=True)
        cursor.close()
    finally:
        connection.close()
    if not blocks:
        raise ValueError("La vista no devolvió registros.")
    data = pd.concat(blocks, ignore_index=True)
    if data.transaction_id.isna().any() or data.transaction_id.duplicated().any():
        raise ValueError("Hay identificadores nulos o duplicados.")
    y = pd.to_numeric(data.is_fraud, errors="raise")
    if y.isna().any() or not y.isin([0, 1]).all():
        raise ValueError("is_fraud debe contener exclusivamente 0 y 1.")
    data["is_fraud"] = y.astype("int8")
    if len(data) != 990261 or int(y.sum()) != 1413:
        raise ValueError("La muestra no coincide con S9 (990.261 filas, 1.413 fraudes). Se detuvo sin exportar.")
    train, validation, test = original_splits(y)
    counts = {name: {"rows": len(idx), "frauds": int(y.iloc[idx].sum())}
              for name, idx in [("train", train), ("validation", validation), ("test", test)]}
    if counts != {"train": {"rows": 693182, "frauds": 989},
                  "validation": {"rows": 148539, "frauds": 212},
                  "test": {"rows": 148540, "frauds": 212}}:
        raise ValueError(f"Las particiones no coinciden con S9: {counts}")
    development_indices = np.sort(np.concatenate([train, validation]))
    if np.intersect1d(development_indices, test).size:
        raise AssertionError("Solapamiento con el test.")
    development = data.iloc[development_indices].copy()
    test_ids = np.sort(data.transaction_id.iloc[test].to_numpy(dtype=np.int64))
    test_hash = hashlib.sha256(test_ids.astype("<i8").tobytes()).hexdigest()
    if test_hash != "3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08":
        raise ValueError("Los IDs de test no coinciden con S9; no se exporta una partición distinta.")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = development.to_csv(index=False).encode("utf-8")
    if str(output).endswith(".gz"):
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
        gzip.decompress(payload)
    temporary = output.with_name(output.name + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(output)
    info = {
        "status": "development_only", "file_sha256": sha256(output),
        "rows": len(development), "frauds": int(development.is_fraud.sum()),
        "original_split": counts, "test_excluded": True,
        "excluded_test_ids_sha256": hashlib.sha256(test_ids.astype("<i8").tobytes()).hexdigest(),
        "split_procedure": "CHECKSUM(id,42)%9=0; ORDER BY id; stratified 70/15/15 seed42",
        "sklearn_version": importlib.metadata.version("scikit-learn"),
        "numpy_version": np.__version__, "pandas_version": pd.__version__,
        "source_commit": "deb64c1d630b4c97d1318ff9a727dc1e1c377c04",
        "note": "Partición reconstruida con el procedimiento S9; no se entrenó ni evaluó ningún modelo.",
    }
    manifest.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo: {output.name} y {manifest.name}")
    print("841.721 filas de desarrollo. Test S9 excluido; la base no fue modificada.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"ERROR: {exc}")
