"""Verifica los cinco archivos públicos antes de cargarlos en FraudeDB."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PUBLIC_SOURCE = (
    "https://www.kaggle.com/datasets/"
    "computingvictor/transactions-fraud-datasets/data"
)

CSV_HEADERS = {
    "users_data.csv": [
        "id",
        "current_age",
        "retirement_age",
        "birth_year",
        "birth_month",
        "gender",
        "address",
        "latitude",
        "longitude",
        "per_capita_income",
        "yearly_income",
        "total_debt",
        "credit_score",
        "num_credit_cards",
    ],
    "cards_data.csv": [
        "id",
        "client_id",
        "card_brand",
        "card_type",
        "card_number",
        "expires",
        "cvv",
        "has_chip",
        "num_cards_issued",
        "credit_limit",
        "acct_open_date",
        "year_pin_last_changed",
        "card_on_dark_web",
    ],
    "transactions_data.csv": [
        "id",
        "date",
        "client_id",
        "card_id",
        "amount",
        "use_chip",
        "merchant_id",
        "merchant_city",
        "merchant_state",
        "zip",
        "mcc",
        "errors",
    ],
}

JSON_FILES = ["train_fraud_labels.json", "mcc_codes.json"]
LABEL_PAIR = re.compile(r'"(?P<id>\d+)"\s*:\s*"(?P<label>Yes|No)"')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        required=True,
        type=Path,
        help="Carpeta que contiene los tres CSV y los dos JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Ruta opcional para guardar el manifiesto JSON.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count_csv_rows(path: Path) -> int:
    lines = 0
    last = b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            lines += block.count(b"\n")
            last = block[-1:]
    if last and last != b"\n":
        lines += 1
    return max(0, lines - 1)


def read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return next(csv.reader(stream), [])


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
            total += sum(bool(LABEL_PAIR.search(part)) for part in parts)
    return total + int(bool(LABEL_PAIR.search(carry)))


def inspect(source_dir: Path) -> list[dict[str, object]]:
    expected = [*CSV_HEADERS, *JSON_FILES]
    missing = [name for name in expected if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos fuente: " + ", ".join(sorted(missing))
        )

    results: list[dict[str, object]] = []
    for name, expected_header in CSV_HEADERS.items():
        path = source_dir / name
        actual_header = read_csv_header(path)
        if actual_header != expected_header:
            raise ValueError(
                f"Encabezado inesperado en {name}: {actual_header}"
            )
        results.append(
            {
                "name": name,
                "size_bytes": path.stat().st_size,
                "row_count": count_csv_rows(path),
                "sha256": sha256(path),
            }
        )

    labels = source_dir / "train_fraud_labels.json"
    results.append(
        {
            "name": labels.name,
            "size_bytes": labels.stat().st_size,
            "row_count": count_label_rows(labels),
            "sha256": sha256(labels),
        }
    )

    mcc = source_dir / "mcc_codes.json"
    with mcc.open("r", encoding="utf-8") as stream:
        mcc_data = json.load(stream)
    if not isinstance(mcc_data, dict):
        raise ValueError("mcc_codes.json no contiene el objeto esperado.")
    results.append(
        {
            "name": mcc.name,
            "size_bytes": mcc.stat().st_size,
            "row_count": len(mcc_data),
            "sha256": sha256(mcc),
        }
    )
    return results


def main() -> int:
    args = parse_args()
    try:
        source_dir = args.source_dir.resolve()
        files = inspect(source_dir)
        manifest = {
            "dataset_name": "Transactions Fraud Datasets",
            "public_source": PUBLIC_SOURCE,
            "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "source_files": files,
        }
        if args.output:
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Manifiesto guardado: {output}")

        print("ARCHIVOS FUENTE VÁLIDOS")
        for item in files:
            print(
                f"- {item['name']}: {item['row_count']:,} filas; "
                f"SHA-256 {item['sha256']}"
            )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
