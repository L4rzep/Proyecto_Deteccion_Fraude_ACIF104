"""Evalúa variables candidatas antes del modelamiento de FINAN.

El programa no entrena modelos ni modifica FraudeDB. Crea una muestra
determinística en una tabla temporal, mide completitud, cardinalidad y señal
univariada, y guarda resultados para decidir qué variables pasan a las pruebas
de modelos. Una asociación aislada no demuestra causalidad ni garantiza que
la variable mejore un modelo combinado.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    import pyodbc


NUMERIC_FEATURES = [
    "amount",
    "amount_signed_log",
    "current_age",
    "age_at_transaction",
    "retirement_age",
    "per_capita_income",
    "yearly_income",
    "total_debt",
    "credit_score",
    "num_credit_cards",
    "num_cards_issued",
    "credit_limit",
    "account_open_year",
    "years_since_pin_change",
    "amount_to_credit_limit",
    "amount_to_yearly_income",
    "card_account_age_years",
    "months_to_card_expiration",
]

CATEGORICAL_FEATURES = [
    "transaction_hour",
    "day_of_week",
    "is_weekend",
    "transaction_month",
    "use_chip",
    "merchant_city",
    "merchant_state",
    "merchant_zip",
    "mcc",
    "gender",
    "card_brand",
    "card_type",
    "has_chip",
    "account_open_month",
]

DERIVED_FEATURE = {
    "column_name": "amount_signed_log",
    "source_reference": "derived_from_amount",
    "sql_type": "float",
    "role": "predictor",
    "available_before_prediction": "yes",
    "initial_model_use": "compare_with_amount",
    "description": (
        "Transformación logarítmica con signo que reduce la escala de montos "
        "altos sin convertir devoluciones negativas en compras positivas"
    ),
}

DECISION_OVERRIDES = {
    "transaction_id": (
        "exclude",
        "Identifica la fila, pero no describe el comportamiento de la transacción.",
    ),
    "transaction_date": (
        "use_derived_only",
        "Se usan hora, día y mes; la fecha completa podría memorizar periodos.",
    ),
    "client_id": (
        "exclude",
        "Se conserva para integrar datos, no como predictor.",
    ),
    "card_id": (
        "exclude",
        "Se conserva para integrar datos, no como predictor.",
    ),
    "merchant_id": (
        "exclude",
        "Su cardinalidad elevada puede memorizar comercios concretos.",
    ),
    "merchant_city": (
        "hold_cardinality_review",
        "El informe anterior la excluyó por cardinalidad; ahora se mide antes de decidir.",
    ),
    "merchant_zip": (
        "hold_cardinality_review",
        "Puede generar demasiadas categorías y memorizar zonas específicas.",
    ),
    "current_age": (
        "hold_temporal_review",
        "Se compara con el informe anterior, pero se prefiere age_at_transaction.",
    ),
    "gender": (
        "hold_fairness_review",
        "Se mide para auditoría, pero no se aprueba como predictor sin revisar equidad.",
    ),
    "per_capita_income": (
        "hold_temporal_review",
        "La fuente entrega una fotografía del cliente cuya fecha histórica debe confirmarse.",
    ),
    "yearly_income": (
        "hold_temporal_review",
        "La fuente entrega una fotografía del cliente cuya fecha histórica debe confirmarse.",
    ),
    "total_debt": (
        "hold_temporal_review",
        "La fuente entrega una fotografía del cliente cuya fecha histórica debe confirmarse.",
    ),
    "credit_score": (
        "hold_temporal_review",
        "La fuente entrega una fotografía del cliente cuya fecha histórica debe confirmarse.",
    ),
    "credit_limit": (
        "hold_temporal_review",
        "Debe confirmarse que el límite corresponde al momento de la transacción.",
    ),
    "account_open_month": (
        "prefer_derived_version",
        "Se prioriza card_account_age_years, que expresa antigüedad en la fecha de compra.",
    ),
    "account_open_year": (
        "prefer_derived_version",
        "Se prioriza card_account_age_years, que expresa antigüedad en la fecha de compra.",
    ),
    "mcc_description": (
        "exclude_duplicate_use_mcc",
        "Se mantiene para interpretar resultados; el modelo evaluará el código MCC.",
    ),
    "amount_to_yearly_income": (
        "hold_temporal_review",
        "Su uso depende de confirmar la vigencia temporal del ingreso anual.",
    ),
    "amount_signed_log": (
        "compare_with_amount",
        "Se comparará con amount; no se eliminarán los montos atípicos.",
    ),
    "is_fraud": (
        "target_only",
        "Es la respuesta que se busca predecir y nunca una entrada del modelo.",
    ),
}


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
        "--dictionary",
        type=Path,
        default=root / "data" / "reference" / "data_dictionary.csv",
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
        default=9,
        help="Aproximadamente una de cada N filas integra la muestra.",
    )
    parser.add_argument(
        "--minimum-category-rows",
        type=int,
        default=5_000,
        help="Soporte mínimo para usar una categoría al calcular la señal.",
    )
    parser.add_argument(
        "--max-category-details",
        type=int,
        default=100,
        help="Máximo de categorías guardadas por variable en el detalle.",
    )
    return parser.parse_args()


def connect(args: argparse.Namespace) -> pyodbc.Connection:
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


def read_dictionary(path: Path) -> list[dict[str, str]]:
    with path.resolve().open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "column_name" not in rows[0]:
        raise ValueError("El diccionario de datos no tiene la estructura esperada")
    return rows


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


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no válido: {name}")
    return f"[{name}]"


def validate_schema(
    connection: pyodbc.Connection, dictionary: list[dict[str, str]]
) -> None:
    if not connection.execute(
        "SELECT CASE WHEN OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') "
        "IS NULL THEN 0 ELSE 1 END"
    ).fetchval():
        raise RuntimeError("No existe dbo.vw_dataset_maestro")

    actual = {
        str(row[0])
        for row in connection.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'vw_dataset_maestro'"
        ).fetchall()
    }
    expected = {row["column_name"] for row in dictionary}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "Faltan variables del diccionario en la vista: " + ", ".join(missing)
        )


def create_sample(
    connection: pyodbc.Connection, seed: int, modulo: int
) -> dict[str, int]:
    selected = list(dict.fromkeys(NUMERIC_FEATURES + CATEGORICAL_FEATURES))
    selected.remove("amount_signed_log")
    column_sql = ",\n        ".join(quote_identifier(name) for name in selected)
    derived_amount = """
        CASE
            WHEN amount IS NULL THEN NULL
            WHEN amount < 0
                THEN -LOG(1.0 + ABS(CONVERT(float, amount)))
            ELSE LOG(1.0 + ABS(CONVERT(float, amount)))
        END AS amount_signed_log
    """
    connection.execute(
        "IF OBJECT_ID('tempdb..#finan_feature_sample') IS NOT NULL "
        "DROP TABLE #finan_feature_sample"
    )
    # Se insertan únicamente enteros ya validados. En SQL Server, una tabla
    # temporal creada mediante una consulta parametrizada puede quedar dentro
    # del alcance interno de esa ejecución y desaparecer al terminarla.
    safe_seed = int(seed)
    safe_modulo = int(modulo)
    connection.execute(
        f"""
        SELECT
            {column_sql},
            {derived_amount},
            is_fraud
        INTO #finan_feature_sample
        FROM dbo.vw_dataset_maestro
        WHERE (CHECKSUM(transaction_id, {safe_seed}) & 2147483647)
              % {safe_modulo} = 0
        """
    )
    row = connection.execute(
        "SELECT COUNT_BIG(*) AS sample_rows, "
        "SUM(CONVERT(bigint, is_fraud)) AS fraud_rows "
        "FROM #finan_feature_sample"
    ).fetchone()
    result = {"sample_rows": int(row[0]), "fraud_rows": int(row[1])}
    if result["sample_rows"] == 0 or result["fraud_rows"] < 100:
        raise RuntimeError(
            "La muestra no contiene suficientes fraudes para una revisión estable"
        )
    return result


def quality_summary(connection: pyodbc.Connection) -> dict[str, dict[str, int]]:
    features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    expressions = ["COUNT_BIG(*) AS [total_rows]"]
    for feature in features:
        identifier = quote_identifier(feature)
        expressions.extend(
            [
                f"SUM(CASE WHEN {identifier} IS NULL THEN 1 ELSE 0 END) "
                f"AS [{feature}__null_rows]",
                f"APPROX_COUNT_DISTINCT({identifier}) "
                f"AS [{feature}__distinct]",
            ]
        )
    row = rows_as_dicts(
        connection,
        "SELECT\n" + ",\n".join(expressions) + "\nFROM #finan_feature_sample",
    )[0]
    total = int(row["total_rows"])
    return {
        feature: {
            "total_rows": total,
            "null_rows": int(row[f"{feature}__null_rows"]),
            "approx_distinct": int(row[f"{feature}__distinct"]),
        }
        for feature in features
    }


def numeric_summaries(
    connection: pyodbc.Connection,
) -> dict[str, dict[int, dict[str, float | int | None]]]:
    expressions = ["is_fraud"]
    for feature in NUMERIC_FEATURES:
        identifier = quote_identifier(feature)
        value = f"CONVERT(float, {identifier})"
        expressions.extend(
            [
                f"COUNT({identifier}) AS [{feature}__count]",
                f"AVG({value}) AS [{feature}__mean]",
                f"STDEV({value}) AS [{feature}__stdev]",
                f"MIN({value}) AS [{feature}__minimum]",
                f"MAX({value}) AS [{feature}__maximum]",
            ]
        )
    rows = rows_as_dicts(
        connection,
        "SELECT\n"
        + ",\n".join(expressions)
        + "\nFROM #finan_feature_sample GROUP BY is_fraud ORDER BY is_fraud",
    )
    result: dict[str, dict[int, dict[str, float | int | None]]] = {
        feature: {} for feature in NUMERIC_FEATURES
    }
    for row in rows:
        label = int(row["is_fraud"])
        for feature in NUMERIC_FEATURES:
            result[feature][label] = {
                "count": int(row[f"{feature}__count"]),
                "mean": to_float(row[f"{feature}__mean"]),
                "stdev": to_float(row[f"{feature}__stdev"]),
                "minimum": to_float(row[f"{feature}__minimum"]),
                "maximum": to_float(row[f"{feature}__maximum"]),
            }
    return result


def categorical_summaries(
    connection: pyodbc.Connection,
    total_rows: int,
    fraud_rows: int,
    minimum_rows: int,
    max_details: int,
) -> tuple[dict[str, dict[str, float | int]], list[dict[str, Any]]]:
    global_rate = fraud_rows / total_rows
    summaries: dict[str, dict[str, float | int]] = {}
    details: list[dict[str, Any]] = []

    for feature in CATEGORICAL_FEATURES:
        identifier = quote_identifier(feature)
        rows = rows_as_dicts(
            connection,
            f"""
            SELECT
                CONVERT(nvarchar(255), {identifier}) AS category_value,
                COUNT_BIG(*) AS transactions,
                SUM(CONVERT(bigint, is_fraud)) AS frauds
            FROM #finan_feature_sample
            GROUP BY {identifier}
            ORDER BY transactions DESC, category_value
            """,
        )
        weighted_difference = 0.0
        supported_rates: list[float] = []
        for position, row in enumerate(rows):
            transactions = int(row["transactions"])
            frauds = int(row["frauds"])
            rate = frauds / transactions if transactions else 0.0
            supported = transactions >= minimum_rows
            if supported:
                supported_rates.append(rate)
                weighted_difference += (
                    transactions / total_rows
                ) * abs(rate - global_rate)
            if position < max_details:
                details.append(
                    {
                        "feature": feature,
                        "category_value": (
                            "<NULL>"
                            if row["category_value"] is None
                            else str(row["category_value"])
                        ),
                        "transactions": transactions,
                        "frauds": frauds,
                        "fraud_rate_pct": round(100.0 * rate, 6),
                        "supported_for_signal": "yes" if supported else "no",
                    }
                )

        minimum_rate = min(supported_rates) if supported_rates else 0.0
        maximum_rate = max(supported_rates) if supported_rates else 0.0
        summaries[feature] = {
            "relative_rate_variation": (
                weighted_difference / global_rate if global_rate else 0.0
            ),
            "minimum_supported_rate": minimum_rate,
            "maximum_supported_rate": maximum_rate,
            "maximum_supported_lift": (
                maximum_rate / global_rate if global_rate else 0.0
            ),
            "supported_categories": len(supported_rates),
        }
    return summaries, details


def to_float(value: Any) -> float | None:
    return None if value is None else float(value)


def standardized_mean_difference(
    class_zero: dict[str, Any], class_one: dict[str, Any]
) -> float | None:
    mean_zero = class_zero.get("mean")
    mean_one = class_one.get("mean")
    sd_zero = class_zero.get("stdev")
    sd_one = class_one.get("stdev")
    if None in (mean_zero, mean_one, sd_zero, sd_one):
        return None
    pooled = math.sqrt((float(sd_zero) ** 2 + float(sd_one) ** 2) / 2.0)
    if pooled == 0:
        return 0.0
    return abs(float(mean_one) - float(mean_zero)) / pooled


def provisional_decision(row: dict[str, str]) -> tuple[str, str]:
    feature = row["column_name"]
    if feature in DECISION_OVERRIDES:
        return DECISION_OVERRIDES[feature]
    initial = row["initial_model_use"]
    mapping = {
        "candidate": (
            "candidate",
            "Puede pasar a la comparación de modelos si su calidad es suficiente.",
        ),
        "review": (
            "evaluate_then_decide",
            "Su uso se decidirá con estos resultados y la validación del modelo.",
        ),
        "review_temporal": (
            "hold_temporal_review",
            "Debe confirmarse que el valor estaba disponible en la fecha de la transacción.",
        ),
        "review_high_cardinality": (
            "hold_cardinality_review",
            "Debe demostrar aporte sin producir demasiadas categorías.",
        ),
        "audit_before_use": (
            "hold_fairness_review",
            "Requiere revisión de equidad antes de incorporarse al modelo.",
        ),
    }
    return mapping.get(
        initial,
        ("evaluate_then_decide", "La decisión final depende de la evidencia obtenida."),
    )


def assessment_rows(
    dictionary: list[dict[str, str]],
    quality: dict[str, dict[str, int]],
    numeric: dict[str, dict[int, dict[str, Any]]],
    categorical: dict[str, dict[str, float | int]],
) -> list[dict[str, Any]]:
    source_rows = [*dictionary, DERIVED_FEATURE]
    output: list[dict[str, Any]] = []
    for source in source_rows:
        feature = source["column_name"]
        decision, reason = provisional_decision(source)
        quality_row = quality.get(feature)
        base = {
            "feature": feature,
            "source_reference": source["source_reference"],
            "role": source["role"],
            "analysis_kind": "not_analyzed",
            "total_rows": "",
            "non_null_rows": "",
            "null_pct": "",
            "approx_distinct": "",
            "signal_measure": "",
            "signal_value": "",
            "class_0_mean": "",
            "class_1_mean": "",
            "minimum_supported_fraud_rate_pct": "",
            "maximum_supported_fraud_rate_pct": "",
            "maximum_supported_lift": "",
            "provisional_use": decision,
            "reason": reason,
            "evidence_scope": "univariate_not_causal",
        }
        if quality_row:
            total = quality_row["total_rows"]
            null_rows = quality_row["null_rows"]
            base.update(
                {
                    "total_rows": total,
                    "non_null_rows": total - null_rows,
                    "null_pct": round(100.0 * null_rows / total, 6),
                    "approx_distinct": quality_row["approx_distinct"],
                }
            )

        if feature in numeric:
            class_zero = numeric[feature].get(0, {})
            class_one = numeric[feature].get(1, {})
            signal = standardized_mean_difference(class_zero, class_one)
            base.update(
                {
                    "analysis_kind": "numeric_class_comparison",
                    "signal_measure": "standardized_mean_difference",
                    "signal_value": "" if signal is None else round(signal, 6),
                    "class_0_mean": optional_round(class_zero.get("mean")),
                    "class_1_mean": optional_round(class_one.get("mean")),
                }
            )
        elif feature in categorical:
            summary = categorical[feature]
            base.update(
                {
                    "analysis_kind": "categorical_fraud_rate",
                    "signal_measure": "relative_rate_variation",
                    "signal_value": round(
                        float(summary["relative_rate_variation"]), 6
                    ),
                    "minimum_supported_fraud_rate_pct": round(
                        100.0 * float(summary["minimum_supported_rate"]), 6
                    ),
                    "maximum_supported_fraud_rate_pct": round(
                        100.0 * float(summary["maximum_supported_rate"]), 6
                    ),
                    "maximum_supported_lift": round(
                        float(summary["maximum_supported_lift"]), 6
                    ),
                }
            )
        output.append(base)
    return output


def optional_round(value: Any) -> float | str:
    return "" if value is None else round(float(value), 6)


def main() -> int:
    args = parse_args()
    if args.sample_modulo <= 0:
        raise ValueError("--sample-modulo debe ser positivo")
    if args.minimum_category_rows <= 0:
        raise ValueError("--minimum-category-rows debe ser positivo")
    if args.max_category_details <= 0:
        raise ValueError("--max-category-details debe ser positivo")

    dictionary = read_dictionary(args.dictionary)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = connect(args)
    try:
        validate_schema(connection, dictionary)
        sample = create_sample(
            connection, seed=args.seed, modulo=args.sample_modulo
        )
        print(
            "Muestra preparada: "
            f"{sample['sample_rows']:,} filas; "
            f"{sample['fraud_rows']:,} fraudes."
        )
        quality = quality_summary(connection)
        numeric = numeric_summaries(connection)
        categorical, category_details = categorical_summaries(
            connection,
            total_rows=sample["sample_rows"],
            fraud_rows=sample["fraud_rows"],
            minimum_rows=args.minimum_category_rows,
            max_details=args.max_category_details,
        )
        assessment = assessment_rows(
            dictionary, quality, numeric, categorical
        )

        write_csv(
            output_dir / "feature_candidate_assessment.csv", assessment
        )
        write_csv(
            output_dir / "feature_category_rates.csv", category_details
        )
        metadata = {
            "database": args.database,
            "seed": args.seed,
            "sample_modulo": args.sample_modulo,
            "sample_rows": sample["sample_rows"],
            "fraud_rows": sample["fraud_rows"],
            "fraud_rate_pct": round(
                100.0 * sample["fraud_rows"] / sample["sample_rows"], 6
            ),
            "minimum_category_rows": args.minimum_category_rows,
            "numeric_signal": "standardized_mean_difference",
            "categorical_signal": "relative_rate_variation",
            "scope": (
                "Análisis univariado previo al modelamiento; no entrena modelos "
                "ni aprueba automáticamente variables."
            ),
        }
        (output_dir / "feature_assessment_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        connection.close()

    print(f"Evaluación de variables guardada en: {output_dir}")
    print("Archivos generados:")
    print("- feature_candidate_assessment.csv")
    print("- feature_category_rates.csv")
    print("- feature_assessment_metadata.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
