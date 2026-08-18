"""Compara tres arquitecturas MLP con la misma evidencia del proyecto.

Utiliza la configuracion de variables ampliada, la estrategia sin balanceo y
la division estratificada 70/15/15 seleccionadas en las etapas anteriores.
Compara tres topologias de red neuronal unicamente con validacion. El conjunto
de prueba se separa y cuenta, pero no se transforma, predice ni utiliza.
"""

from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any


ARCHITECTURES = [
    "mlp_basic_64",
    "mlp_deep_l2_128_64_32",
    "mlp_wide_adam_256_128_64",
]
ARCHITECTURE_LABELS = {
    "mlp_basic_64": "MLP basica 64",
    "mlp_deep_l2_128_64_32": "MLP profunda 128-64-32",
    "mlp_wide_adam_256_128_64": "MLP amplia 256-128-64",
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-modulo", type=int, default=9)
    parser.add_argument("--fetch-size", type=int, default=50_000)
    parser.add_argument("--max-epochs", type=int, default=15)
    parser.add_argument("--min-epochs", type=int, default=4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--min-delta", type=float, default=0.0001)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument(
        "--device",
        choices=["cuda", "cpu"],
        default="cuda",
        help="Dispositivo de entrenamiento. La ejecucion oficial usa cuda.",
    )
    parser.add_argument(
        "--feature-selection-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "feature_configuration_selected.json",
    )
    parser.add_argument(
        "--balancing-selection-file",
        type=Path,
        default=root
        / "results"
        / "models"
        / "balancing_strategy_selected.json",
    )
    parser.add_argument(
        "--ml-selection-file",
        type=Path,
        default=root / "results" / "models" / "ml_model_selected.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results" / "models",
    )
    return parser.parse_args()


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Nombre de variable no valido: {name}")
    return f"[{name}]"


def read_json(path: Path) -> dict[str, Any]:
    with path.resolve().open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_selections(
    args: argparse.Namespace,
) -> tuple[list[str], list[str], dict[str, Any]]:
    feature_selection = read_json(args.feature_selection_file)
    numeric = list(feature_selection.get("numeric_features", []))
    categorical = list(feature_selection.get("categorical_features", []))
    if not numeric or not categorical:
        raise ValueError("La configuracion seleccionada no contiene variables")
    if "is_fraud" in numeric + categorical:
        raise ValueError("is_fraud no puede formar parte de las entradas")
    if len(numeric + categorical) != len(set(numeric + categorical)):
        raise ValueError("La configuracion contiene variables duplicadas")

    balancing_selection = read_json(args.balancing_selection_file)
    if balancing_selection.get("scenario") != "no_balancing":
        raise ValueError(
            "La comparacion DL esperaba la estrategia seleccionada "
            "no_balancing"
        )
    if balancing_selection.get("test_used") is not False:
        raise ValueError("La seleccion de balanceo no confirma el test reservado")

    ml_selection = read_json(args.ml_selection_file)
    if ml_selection.get("test_used") is not False:
        raise ValueError("La seleccion ML no confirma el test reservado")
    return numeric, categorical, ml_selection


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


def validate_schema(
    connection: Any, numeric: list[str], categorical: list[str]
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
    expected = {*numeric, *categorical, "transaction_id", "is_fraud"}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "Faltan variables requeridas en la vista: " + ", ".join(missing)
        )


def load_sample(
    connection: Any,
    args: argparse.Namespace,
    numeric: list[str],
    categorical: list[str],
) -> Any:
    import pandas as pd

    features = list(dict.fromkeys(numeric + categorical))
    columns_sql = ", ".join(quote_identifier(name) for name in features)
    safe_seed = int(args.seed)
    safe_modulo = int(args.sample_modulo)
    query = f"""
        SELECT transaction_id, {columns_sql}, is_fraud
        FROM dbo.vw_dataset_maestro
        WHERE (CHECKSUM(transaction_id, {safe_seed}) & 2147483647)
              % {safe_modulo} = 0
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
        print(f"Datos leidos: {loaded:,} filas", flush=True)
    cursor.close()
    if not blocks:
        raise RuntimeError("La muestra de modelamiento quedo vacia")
    data = pd.concat(blocks, ignore_index=True)
    del blocks
    data.drop(columns=["transaction_id"], inplace=True)
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["is_fraud"] = data["is_fraud"].astype("int8")
    return data


def split_indices(target: Any, seed: int) -> tuple[Any, Any, Any]:
    import numpy as np
    from sklearn.model_selection import train_test_split

    all_indices = np.arange(len(target))
    train_indices, temporary_indices = train_test_split(
        all_indices,
        test_size=0.30,
        random_state=seed,
        stratify=target,
    )
    validation_indices, test_indices = train_test_split(
        temporary_indices,
        test_size=0.50,
        random_state=seed,
        stratify=target.iloc[temporary_indices],
    )
    return train_indices, validation_indices, test_indices


def class_counts(target: Any, indices: Any) -> dict[str, int]:
    subset = target.iloc[indices]
    return {
        "rows": int(len(subset)),
        "frauds": int(subset.sum()),
        "non_frauds": int((subset == 0).sum()),
    }


def prepare_matrices(
    train_data: Any,
    validation_data: Any,
    numeric: list[str],
    categorical: list[str],
) -> tuple[Any, Any, dict[str, Any]]:
    from scipy import sparse
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

    numeric_imputer = SimpleImputer(strategy="median")
    numeric_scaler = StandardScaler()
    train_numeric = numeric_scaler.fit_transform(
        numeric_imputer.fit_transform(train_data[numeric])
    )
    validation_numeric = numeric_scaler.transform(
        numeric_imputer.transform(validation_data[numeric])
    )

    categorical_imputer = SimpleImputer(strategy="most_frequent")
    train_categories = categorical_imputer.fit_transform(
        train_data[categorical]
    )
    validation_categories = categorical_imputer.transform(
        validation_data[categorical]
    )
    ordinal = OrdinalEncoder(
        handle_unknown="use_encoded_value",
        unknown_value=-1,
    )
    train_categories_encoded = ordinal.fit_transform(train_categories)
    validation_categories_encoded = ordinal.transform(validation_categories)
    one_hot = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    train_categorical = one_hot.fit_transform(train_categories_encoded)
    validation_categorical = one_hot.transform(validation_categories_encoded)

    train_matrix = sparse.hstack(
        [sparse.csr_matrix(train_numeric), train_categorical], format="csr"
    )
    validation_matrix = sparse.hstack(
        [sparse.csr_matrix(validation_numeric), validation_categorical],
        format="csr",
    )
    preprocessing = {
        "numeric_imputation": "median",
        "numeric_scaling": "standard",
        "categorical_imputation": "most_frequent",
        "categorical_encoding": "ordinal_then_one_hot",
        "matrix_columns": int(train_matrix.shape[1]),
    }
    return train_matrix, validation_matrix, preprocessing


def architecture_parameters(
    architecture: str, seed: int
) -> dict[str, Any]:
    common = {
        "activation": "relu",
        "optimizer": "adam",
        "learning_rate_init": 0.001,
        "random_state": seed,
    }
    if architecture == "mlp_basic_64":
        return {
            **common,
            "hidden_layer_sizes": [64],
            "dropout": 0.0,
            "weight_decay_l2": 0.0001,
            "adaptive_scheduler": False,
        }
    if architecture == "mlp_deep_l2_128_64_32":
        return {
            **common,
            "hidden_layer_sizes": [128, 64, 32],
            "dropout": 0.20,
            "weight_decay_l2": 0.001,
            "adaptive_scheduler": False,
        }
    if architecture == "mlp_wide_adam_256_128_64":
        return {
            **common,
            "hidden_layer_sizes": [256, 128, 64],
            "dropout": 0.10,
            "weight_decay_l2": 0.0005,
            "learning_rate_init": 0.0005,
            "adaptive_scheduler": True,
        }
    raise ValueError(f"Arquitectura desconocida: {architecture}")


def build_network(
    input_features: int, parameters: dict[str, Any]
) -> Any:
    from torch import nn

    layers: list[Any] = []
    previous = input_features
    hidden_layers = list(parameters["hidden_layer_sizes"])
    dropout = float(parameters["dropout"])
    for units in hidden_layers:
        layers.append(nn.Linear(previous, int(units)))
        layers.append(nn.ReLU())
        if dropout > 0:
            layers.append(nn.Dropout(dropout))
        previous = int(units)
    layers.append(nn.Linear(previous, 1))
    return nn.Sequential(*layers)


def select_device(requested: str, seed: int) -> tuple[Any, dict[str, Any]]:
    import numpy as np
    import torch

    np.random.seed(seed)
    torch.manual_seed(seed)
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA no esta disponible en PyTorch. No se continuara "
                "silenciosamente con CPU."
            )
        device = torch.device("cuda")
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        properties = torch.cuda.get_device_properties(device)
        metadata = {
            "requested": requested,
            "used": "cuda",
            "name": torch.cuda.get_device_name(device),
            "compute_capability": list(torch.cuda.get_device_capability(device)),
            "memory_mib": round(properties.total_memory / (1024**2), 1),
            "torch_cuda_version": torch.version.cuda,
        }
        return device, metadata
    return torch.device("cpu"), {
        "requested": requested,
        "used": "cpu",
        "name": "CPU",
    }


def dense_float32(matrix: Any) -> Any:
    import numpy as np

    return matrix.toarray().astype(np.float32, copy=False)


def best_f1_threshold(target: Any, probabilities: Any) -> float:
    import numpy as np
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(
        target, probabilities
    )
    if thresholds.size == 0:
        return 0.5
    denominator = precision[:-1] + recall[:-1]
    f1_values = np.divide(
        2.0 * precision[:-1] * recall[:-1],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator != 0,
    )
    return float(thresholds[int(np.argmax(f1_values))])


def threshold_metrics(
    target: Any, probabilities: Any, threshold: float, prefix: str
) -> dict[str, Any]:
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    predictions = (probabilities >= threshold).astype("int8")
    precision, recall, f1, _ = precision_recall_fscore_support(
        target,
        predictions,
        average="binary",
        zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(
        target, predictions, labels=[0, 1]
    ).ravel()
    return {
        f"{prefix}_threshold": round(float(threshold), 8),
        f"{prefix}_precision": round(float(precision), 8),
        f"{prefix}_recall": round(float(recall), 8),
        f"{prefix}_f1": round(float(f1), 8),
        f"{prefix}_true_negatives": int(tn),
        f"{prefix}_false_positives": int(fp),
        f"{prefix}_false_negatives": int(fn),
        f"{prefix}_true_positives": int(tp),
    }


def evaluate_architecture(
    architecture: str,
    train_matrix: Any,
    train_target: Any,
    validation_matrix: Any,
    validation_target: Any,
    args: argparse.Namespace,
    device: Any,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    import numpy as np
    import torch
    from sklearn.metrics import average_precision_score, roc_auc_score
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    parameters = architecture_parameters(architecture, args.seed)
    model = build_network(train_matrix.shape[1], parameters).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(parameters["learning_rate_init"]),
        weight_decay=float(parameters["weight_decay_l2"]),
    )
    scheduler = None
    if parameters["adaptive_scheduler"]:
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",
            factor=0.5,
            patience=1,
            min_lr=0.00001,
        )

    train_dataset = TensorDataset(
        torch.from_numpy(train_matrix),
        torch.from_numpy(train_target.astype(np.float32, copy=False)),
    )
    validation_dataset = TensorDataset(
        torch.from_numpy(validation_matrix),
        torch.from_numpy(validation_target.astype(np.float32, copy=False)),
    )
    generator = torch.Generator()
    generator.manual_seed(args.seed)
    pin_memory = device.type == "cuda"
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
        pin_memory=pin_memory,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=max(args.batch_size, 16_384),
        shuffle=False,
        num_workers=0,
        pin_memory=pin_memory,
    )
    label = ARCHITECTURE_LABELS[architecture]
    history: list[dict[str, Any]] = []
    best_pr_auc = -1.0
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    epochs_without_improvement = 0
    training_start = perf_counter()

    for epoch in range(1, args.max_epochs + 1):
        epoch_start = perf_counter()
        model.train()
        running_loss = 0.0
        rows_seen = 0
        total_batches = len(train_loader)
        report_every = max(1, total_batches // 10)
        for batch_number, (features, labels) in enumerate(
            train_loader, start=1
        ):
            features = features.to(device, non_blocking=pin_memory)
            labels = labels.to(device, non_blocking=pin_memory)
            optimizer.zero_grad(set_to_none=True)
            logits = model(features).squeeze(1)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            batch_rows = int(labels.shape[0])
            running_loss += float(loss.detach().cpu()) * batch_rows
            rows_seen += batch_rows
            if batch_number % report_every == 0 or batch_number == total_batches:
                print(
                    f"    epoca {epoch}: "
                    f"{batch_number / total_batches:.0%} de lotes",
                    flush=True,
                )

        model.eval()
        probability_blocks = []
        with torch.no_grad():
            for features, _ in validation_loader:
                features = features.to(device, non_blocking=pin_memory)
                logits = model(features).squeeze(1)
                probability_blocks.append(
                    torch.sigmoid(logits).detach().cpu().numpy()
                )
        probabilities = np.concatenate(probability_blocks)
        pr_auc = float(
            average_precision_score(validation_target, probabilities)
        )
        roc_auc = float(roc_auc_score(validation_target, probabilities))
        training_loss = running_loss / rows_seen
        if scheduler is not None:
            scheduler.step(pr_auc)
        current_learning_rate = float(optimizer.param_groups[0]["lr"])
        epoch_seconds = perf_counter() - epoch_start
        history.append(
            {
                "architecture": architecture,
                "epoch": epoch,
                "training_loss": round(float(training_loss), 8),
                "validation_pr_auc": round(pr_auc, 8),
                "validation_roc_auc": round(roc_auc, 8),
                "learning_rate": round(current_learning_rate, 8),
                "epoch_seconds": round(float(epoch_seconds), 4),
            }
        )
        print(
            f"  [{label}] epoca {epoch}/{args.max_epochs} "
            f"({epoch / args.max_epochs:.0%}); "
            f"loss={training_loss:.6f}; PR-AUC={pr_auc:.6f}; "
            f"tiempo={epoch_seconds:.1f} s",
            flush=True,
        )
        if pr_auc > best_pr_auc + args.min_delta:
            best_pr_auc = pr_auc
            best_epoch = epoch
            best_state = {
                name: tensor.detach().cpu().clone()
                for name, tensor in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        if (
            epoch >= args.min_epochs
            and epochs_without_improvement >= args.patience
        ):
            print(
                f"  [{label}] detencion temprana: no mejoro PR-AUC "
                f"durante {args.patience} epocas.",
                flush=True,
            )
            break

    training_seconds = perf_counter() - training_start
    if best_state is None:
        raise RuntimeError("No fue posible conservar un estado valido de la red")
    model.load_state_dict(best_state)
    model.eval()
    prediction_start = perf_counter()
    probability_blocks = []
    with torch.no_grad():
        for features, _ in validation_loader:
            features = features.to(device, non_blocking=pin_memory)
            logits = model(features).squeeze(1)
            probability_blocks.append(
                torch.sigmoid(logits).detach().cpu().numpy()
            )
    probabilities = np.concatenate(probability_blocks)
    prediction_seconds = perf_counter() - prediction_start
    tuned_threshold = best_f1_threshold(validation_target, probabilities)
    result = {
        "architecture": architecture,
        "training_rows": int(train_matrix.shape[0]),
        "training_frauds": int(train_target.sum()),
        "hidden_layers": "-".join(
            str(value) for value in parameters["hidden_layer_sizes"]
        ),
        "device": str(device),
        "epochs_completed": int(len(history)),
        "best_epoch": int(best_epoch),
        "convergence_rule": "validation_pr_auc_with_early_stopping",
        "training_seconds": round(float(training_seconds), 4),
        "validation_prediction_seconds": round(float(prediction_seconds), 4),
        "validation_roc_auc": round(
            float(roc_auc_score(validation_target, probabilities)), 8
        ),
        "validation_pr_auc": round(
            float(average_precision_score(validation_target, probabilities)),
            8,
        ),
        **threshold_metrics(
            validation_target, probabilities, 0.5, "default"
        ),
        **threshold_metrics(
            validation_target, probabilities, tuned_threshold, "tuned"
        ),
        "test_used": "no",
    }
    del (
        model,
        probabilities,
        best_state,
        train_loader,
        validation_loader,
        train_dataset,
        validation_dataset,
    )
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()
    return result, parameters, history


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No hay filas para escribir en {path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_comparison(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    positions = np.arange(len(rows))
    width = 0.19
    figure, axis = plt.subplots(figsize=(12, 6.5))
    series = [
        ("validation_pr_auc", "PR-AUC"),
        ("tuned_precision", "Precision"),
        ("tuned_recall", "Recall"),
        ("tuned_f1", "F1"),
    ]
    for offset, (key, label) in enumerate(series):
        axis.bar(
            positions + (offset - 1.5) * width,
            [float(row[key]) for row in rows],
            width,
            label=label,
        )
    axis.set_xticks(positions)
    axis.set_xticklabels(
        [ARCHITECTURE_LABELS[row["architecture"]] for row in rows],
        rotation=8,
    )
    axis.set_ylim(0, 1)
    axis.set_ylabel("Valor en validacion")
    axis.set_title("Comparacion de arquitecturas de aprendizaje profundo")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def plot_convergence(history: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for architecture in ARCHITECTURES:
        rows = [
            row for row in history if row["architecture"] == architecture
        ]
        axes[0].plot(
            [int(row["epoch"]) for row in rows],
            [float(row["training_loss"]) for row in rows],
            marker="o",
            label=ARCHITECTURE_LABELS[architecture],
        )
        axes[1].plot(
            [int(row["epoch"]) for row in rows],
            [float(row["validation_pr_auc"]) for row in rows],
            marker="o",
            label=ARCHITECTURE_LABELS[architecture],
        )
    axes[0].set_title("Error de entrenamiento por epoca")
    axes[0].set_xlabel("Epoca")
    axes[0].set_ylabel("Loss")
    axes[1].set_title("PR-AUC de validacion por epoca")
    axes[1].set_xlabel("Epoca")
    axes[1].set_ylabel("PR-AUC")
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def package_versions() -> dict[str, str]:
    packages = [
        "numpy",
        "pandas",
        "pyodbc",
        "scipy",
        "scikit-learn",
        "matplotlib",
        "torch",
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def main() -> int:
    args = parse_args()
    if args.sample_modulo <= 0 or args.fetch_size <= 0:
        raise ValueError(
            "El modulo de muestra y el tamano de bloque deben ser positivos"
        )
    if not 1 <= args.min_epochs <= args.max_epochs:
        raise ValueError("min-epochs debe estar entre 1 y max-epochs")
    if args.patience <= 0 or args.min_delta < 0:
        raise ValueError("patience debe ser positivo y min-delta no negativo")
    if args.batch_size <= 0:
        raise ValueError("batch-size debe ser positivo")

    print("Progreso general: 0 % - inicio", flush=True)
    device, device_metadata = select_device(args.device, args.seed)
    print(
        f"Dispositivo: {device_metadata['used']} - "
        f"{device_metadata['name']}",
        flush=True,
    )
    numeric, categorical, ml_selection = read_selections(args)
    connection = connect(args)
    try:
        validate_schema(connection, numeric, categorical)
        data = load_sample(connection, args, numeric, categorical)
    finally:
        connection.close()
    print("Progreso general: 15 % - muestra cargada", flush=True)

    sample_rows = int(len(data))
    target = data["is_fraud"]
    sample_frauds = int(target.sum())
    train_indices, validation_indices, test_indices = split_indices(
        target, args.seed
    )
    split_summary = {
        "train": class_counts(target, train_indices),
        "validation": class_counts(target, validation_indices),
        "test_reserved": class_counts(target, test_indices),
    }
    train_data = data.iloc[train_indices][numeric + categorical]
    validation_data = data.iloc[validation_indices][numeric + categorical]
    train_target = target.iloc[train_indices].to_numpy(dtype="int8")
    validation_target = target.iloc[validation_indices].to_numpy(dtype="int8")
    del data, target
    train_matrix, validation_matrix, preprocessing = prepare_matrices(
        train_data,
        validation_data,
        numeric,
        categorical,
    )
    del train_data, validation_data
    train_matrix = dense_float32(train_matrix)
    validation_matrix = dense_float32(validation_matrix)
    gc.collect()
    print(
        "Matriz preparada: "
        f"{train_matrix.shape[0]:,} filas y "
        f"{train_matrix.shape[1]:,} columnas."
    )
    print("Progreso general: 25 % - datos preparados", flush=True)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    complete_history: list[dict[str, Any]] = []
    parameters: dict[str, dict[str, Any]] = {}
    progress_after = [48, 71, 94]
    for position, architecture in enumerate(ARCHITECTURES, start=1):
        print(
            f"Evaluando {position}/{len(ARCHITECTURES)}: "
            f"{ARCHITECTURE_LABELS[architecture]}",
            flush=True,
        )
        result, model_parameters, history = evaluate_architecture(
            architecture,
            train_matrix,
            train_target,
            validation_matrix,
            validation_target,
            args,
            device,
        )
        results.append(result)
        complete_history.extend(history)
        parameters[architecture] = model_parameters
        write_csv(output_dir / "dl_architecture_comparison.csv", results)
        write_csv(output_dir / "dl_training_history.csv", complete_history)
        print(
            f"  PR-AUC={result['validation_pr_auc']:.6f}; "
            f"F1={result['tuned_f1']:.6f}; "
            f"Recall={result['tuned_recall']:.6f}; "
            f"Precision={result['tuned_precision']:.6f}; "
            f"mejor epoca={result['best_epoch']}; "
            f"entrenamiento={result['training_seconds']:.2f} s"
        )
        print(
            f"Progreso general: {progress_after[position - 1]} % - "
            f"{ARCHITECTURE_LABELS[architecture]} terminada",
            flush=True,
        )

    winner = sorted(
        results,
        key=lambda row: (
            float(row["validation_pr_auc"]),
            float(row["tuned_f1"]),
            float(row["tuned_recall"]),
        ),
        reverse=True,
    )[0]
    plot_comparison(results, output_dir / "dl_architecture_comparison.png")
    plot_convergence(complete_history, output_dir / "dl_convergence.png")
    selected = {
        "architecture": winner["architecture"],
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "validation_threshold": float(winner["tuned_threshold"]),
        "balancing_strategy": "no_balancing",
        "test_used": False,
        "note": (
            "La arquitectura DL debe compararse con el modelo ML seleccionado "
            "antes de evaluar una sola vez el test final."
        ),
    }
    (output_dir / "dl_architecture_selected.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "database": args.database,
        "seed": args.seed,
        "sample_modulo": args.sample_modulo,
        "sample_rows": sample_rows,
        "sample_frauds": sample_frauds,
        "split": split_summary,
        "feature_configuration": args.feature_selection_file.name,
        "balancing_configuration": args.balancing_selection_file.name,
        "balancing_strategy": "no_balancing",
        "ml_reference": ml_selection,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "preprocessing": preprocessing,
        "device": device_metadata,
        "batch_size": args.batch_size,
        "architectures": ARCHITECTURES,
        "architecture_parameters": parameters,
        "training_control": {
            "max_epochs": args.max_epochs,
            "min_epochs": args.min_epochs,
            "patience": args.patience,
            "min_delta": args.min_delta,
            "best_state_restored": True,
            "selection_metric": "validation_pr_auc",
        },
        "selection_rule": "highest_validation_pr_auc_then_tuned_f1_then_recall",
        "test_policy": (
            "El conjunto de prueba fue separado y contado, pero no fue "
            "transformado, predicho ni utilizado para seleccionar la "
            "arquitectura DL."
        ),
        "package_versions": package_versions(),
    }
    (output_dir / "dl_architecture_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Progreso general: 100 % - resultados guardados", flush=True)
    print(f"Arquitectura DL seleccionada: {winner['architecture']}")
    print(f"Resultados guardados en: {output_dir}")
    print("El conjunto de prueba permanece reservado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
