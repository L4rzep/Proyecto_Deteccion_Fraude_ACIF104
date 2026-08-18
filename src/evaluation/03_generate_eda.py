"""Genera tablas y gráficos EDA reproducibles desde FraudeDB.

El modo normal usa los agregados completos y una muestra determinística para
los gráficos numéricos. ``--quick`` limita todo a 50.000 filas y sirve solo
para comprobar que el flujo funciona; sus resultados no son evidencia final.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyodbc


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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "eda",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--sample-modulo",
        type=int,
        default=45,
        help="Aproximadamente una de cada N filas integra la muestra gráfica.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Valida el flujo con 50.000 filas; no genera evidencia final.",
    )
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
    connection_string = (
        f"DRIVER={{{args.driver}}};SERVER={args.server};"
        f"DATABASE={args.database};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=True, timeout=30)


def rows_as_dicts(
    connection: pyodbc.Connection, sql: str, params: Iterable[Any] = ()
) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, *params)
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No hay filas para guardar en {path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_sql(quick: bool, quick_start: int | None = None) -> str:
    if quick:
        if quick_start is None:
            raise ValueError("Falta el inicio del rango para el modo rápido")
        quick_end = quick_start + 50_000
        return (
            "(SELECT * FROM dbo.vw_dataset_maestro "
            f"WHERE transaction_id >= {quick_start} "
            f"AND transaction_id < {quick_end}) AS source"
        )
    return "dbo.vw_dataset_maestro AS source"


def plot_class_distribution(rows: list[dict[str, Any]], output: Path) -> None:
    labels = ["No fraude" if not row["is_fraud"] else "Fraude" for row in rows]
    values = [int(row["transacciones"]) for row in rows]
    fig, axis = plt.subplots(figsize=(7, 4.5))
    bars = axis.bar(labels, values, color=["#2F6690", "#D1495B"])
    axis.set_yscale("log")
    axis.set_ylabel("Transacciones (escala logarítmica)")
    axis.set_title("Distribución de la variable objetivo")
    axis.bar_label(bars, labels=[f"{value:,}" for value in values], padding=3)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_channel_rates(rows: list[dict[str, Any]], output: Path) -> None:
    ordered = sorted(rows, key=lambda row: float(row["porcentaje_fraude"]))
    labels = [str(row["use_chip"]) for row in ordered]
    values = [float(row["porcentaje_fraude"]) for row in ordered]
    fig, axis = plt.subplots(figsize=(8, 4.5))
    bars = axis.barh(labels, values, color="#3A7D44")
    axis.set_xlabel("Fraude (%)")
    axis.set_title("Tasa de fraude por modalidad de transacción")
    axis.bar_label(bars, labels=[f"{value:.3f}%" for value in values], padding=3)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_mcc_rates(rows: list[dict[str, Any]], output: Path) -> None:
    ordered = list(reversed(rows))
    labels = [f"{row['mcc']} - {row['mcc_description']}" for row in ordered]
    values = [float(row["porcentaje_fraude"]) for row in ordered]
    fig, axis = plt.subplots(figsize=(10, 7))
    bars = axis.barh(labels, values, color="#B56576")
    axis.set_xlabel("Fraude (%)")
    axis.set_title("Categorías MCC con mayor cantidad de fraudes")
    axis.bar_label(bars, labels=[f"{value:.3f}%" for value in values], padding=3)
    axis.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_amount_sample(
    amounts: np.ndarray, labels: np.ndarray, output_dir: Path
) -> None:
    transformed = np.log1p(np.abs(amounts))

    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.hist(transformed, bins=60, color="#6C5B7B", alpha=0.85)
    axis.set_xlabel("log(1 + |monto|)")
    axis.set_ylabel("Transacciones de la muestra")
    axis.set_title("Distribución transformada de la magnitud del monto")
    fig.tight_layout()
    fig.savefig(output_dir / "amount_distribution_log.png", dpi=180)
    plt.close(fig)

    grouped = [transformed[labels == value] for value in (0, 1)]
    fig, axis = plt.subplots(figsize=(7, 4.5))
    axis.boxplot(grouped, tick_labels=["No fraude", "Fraude"], showfliers=False)
    axis.set_ylabel("log(1 + |monto|)")
    axis.set_title("Magnitud del monto según la etiqueta")
    fig.tight_layout()
    fig.savefig(output_dir / "amount_boxplot_by_fraud.png", dpi=180)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    if args.sample_modulo <= 0:
        raise ValueError("--sample-modulo debe ser positivo")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = connect(args)
    try:
        if not connection.execute(
            "SELECT CASE WHEN OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') "
            "IS NULL THEN 0 ELSE 1 END"
        ).fetchval():
            raise RuntimeError("No existe dbo.vw_dataset_maestro")

        quick_start = None
        if args.quick:
            quick_start = int(
                connection.execute(
                    "SELECT MIN(transaction_id) FROM dbo.fraud_labels"
                ).fetchval()
            )
        source = source_sql(args.quick, quick_start)

        class_rows = rows_as_dicts(
            connection,
            f"""
            SELECT is_fraud, COUNT_BIG(*) AS transacciones,
                   CONVERT(decimal(9, 6),
                       100.0 * COUNT_BIG(*) /
                       SUM(COUNT_BIG(*)) OVER ()) AS porcentaje
            FROM {source}
            GROUP BY is_fraud
            ORDER BY is_fraud
            """,
        )
        channel_rows = rows_as_dicts(
            connection,
            f"""
            SELECT use_chip, COUNT_BIG(*) AS transacciones,
                   SUM(CONVERT(bigint, is_fraud)) AS fraudes,
                   CONVERT(decimal(9, 6),
                       100.0 * AVG(CONVERT(float, is_fraud)))
                       AS porcentaje_fraude
            FROM {source}
            GROUP BY use_chip
            ORDER BY use_chip
            """,
        )
        mcc_rows = rows_as_dicts(
            connection,
            f"""
            SELECT TOP (15) mcc, MAX(mcc_description) AS mcc_description,
                   COUNT_BIG(*) AS transacciones,
                   SUM(CONVERT(bigint, is_fraud)) AS fraudes,
                   CONVERT(decimal(9, 6),
                       100.0 * AVG(CONVERT(float, is_fraud)))
                       AS porcentaje_fraude
            FROM {source}
            GROUP BY mcc
            ORDER BY fraudes DESC, mcc
            """,
        )

        if args.quick:
            sample_query = f"""
                SELECT amount, is_fraud
                FROM {source}
                ORDER BY transaction_id
            """
            sample_params: tuple[Any, ...] = ()
        else:
            sample_query = """
                SELECT amount, is_fraud
                FROM dbo.vw_dataset_maestro
                WHERE (CHECKSUM(transaction_id, ?) & 2147483647) % ? = 0
            """
            sample_params = (args.seed, args.sample_modulo)

        sample_cursor = connection.execute(sample_query, *sample_params)
        sample = sample_cursor.fetchall()
        sample_cursor.close()
        if not sample:
            raise RuntimeError("La muestra EDA quedó vacía")

        amounts = np.asarray([float(row[0]) for row in sample], dtype=float)
        labels = np.asarray([int(row[1]) for row in sample], dtype=int)
        sample_rows = [
            {
                "modo": "rapido" if args.quick else "completo",
                "semilla": args.seed,
                "modulo_muestra": args.sample_modulo,
                "filas_muestra": int(amounts.size),
                "fraudes_muestra": int(labels.sum()),
                "porcentaje_fraude_muestra": round(100.0 * labels.mean(), 6),
                "monto_minimo": round(float(amounts.min()), 2),
                "monto_mediana": round(float(np.median(amounts)), 2),
                "monto_promedio": round(float(amounts.mean()), 2),
                "monto_maximo": round(float(amounts.max()), 2),
            }
        ]

        write_csv(output_dir / "class_distribution.csv", class_rows)
        write_csv(output_dir / "use_chip_summary.csv", channel_rows)
        write_csv(output_dir / "top_mcc_summary.csv", mcc_rows)
        write_csv(output_dir / "sample_summary.csv", sample_rows)
        plot_class_distribution(class_rows, output_dir / "class_distribution.png")
        plot_channel_rates(channel_rows, output_dir / "fraud_rate_by_channel.png")
        plot_mcc_rates(mcc_rows, output_dir / "top_mcc_fraud_rate.png")
        plot_amount_sample(amounts, labels, output_dir)

        metadata = {
            "mode": "quick" if args.quick else "full",
            "database": args.database,
            "seed": args.seed,
            "sample_modulo": args.sample_modulo,
            "sample_rows": int(amounts.size),
            "warning": (
                "Validación rápida; no usar como evidencia final."
                if args.quick
                else None
            ),
        }
        (output_dir / "eda_run_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        connection.close()

    print(f"EDA generado correctamente en: {output_dir}")
    print(f"Filas de la muestra gráfica: {len(sample):,}")
    print(f"Fraudes en la muestra gráfica: {int(labels.sum()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
