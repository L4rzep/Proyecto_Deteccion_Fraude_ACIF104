"""Pruebas del contrato del pipeline final; no consultan SQL Server."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "finan_fraud_pipeline.joblib"
SCHEMA_PATH = ROOT / "models" / "finan_feature_schema.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FinalModelContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MODEL_PATH.exists() or not SCHEMA_PATH.exists():
            raise unittest.SkipTest(
                "El pipeline final se genera despues de ejecutar el paso 07"
            )
        import joblib

        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.pipeline = joblib.load(MODEL_PATH)

    def test_hash_matches_schema(self) -> None:
        self.assertEqual(self.schema["model_sha256"], sha256(MODEL_PATH))

    def test_feature_contract(self) -> None:
        numeric = self.schema["numeric_features"]
        categorical = self.schema["categorical_features"]
        ordered = self.schema["ordered_features"]
        self.assertEqual(ordered, numeric + categorical)
        self.assertEqual(len(ordered), len(set(ordered)))
        self.assertNotIn("is_fraud", ordered)
        self.assertNotIn("transaction_id", ordered)

    def test_pipeline_steps_and_probability(self) -> None:
        import pandas as pd

        self.assertEqual(
            list(self.pipeline.named_steps), ["preprocessor", "model"]
        )
        values = {
            name: 0.0 for name in self.schema["numeric_features"]
        }
        values.update(
            {
                name: "CONTRACT_TEST"
                for name in self.schema["categorical_features"]
            }
        )
        frame = pd.DataFrame(
            [[values[name] for name in self.schema["ordered_features"]]],
            columns=self.schema["ordered_features"],
        )
        probabilities = self.pipeline.predict_proba(frame)
        self.assertEqual(probabilities.shape, (1, 2))
        self.assertGreaterEqual(float(probabilities[0, 1]), 0.0)
        self.assertLessEqual(float(probabilities[0, 1]), 1.0)

    def test_threshold_is_valid_and_test_reserved(self) -> None:
        threshold = float(self.schema["threshold"])
        self.assertGreater(threshold, 0.0)
        self.assertLess(threshold, 1.0)
        self.assertIs(self.schema["test_used"], False)


if __name__ == "__main__":
    unittest.main()
