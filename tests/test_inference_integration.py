"""Invoca el proceso real Python, pipeline y SHAP con entradas sintéticas, sin test S9 ni SQL."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InferenceIntegrationTest(unittest.TestCase):
    def invoke(self, value, *extra):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(value))
            result = subprocess.run([sys.executable, str(ROOT / "src/inference/predict_transaction.py"),
                                     "--input-json", str(path), *extra], cwd=ROOT,
                                    capture_output=True, text=True, timeout=60)
        return result

    def fixture(self):
        return json.loads((ROOT / "tests/fixtures/transaccion_sintetica.json").read_text())

    def test_process_prediction_explanation_and_model_identity(self):
        result = self.invoke(self.fixture(), "--explain")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        schema = json.loads((ROOT / "models/finan_feature_schema.json").read_text())
        self.assertEqual(value["status"], "ok")
        self.assertEqual(value["model_sha256"], schema["model_sha256"])
        self.assertEqual(value["threshold"], schema["threshold"])
        self.assertTrue(0 <= value["fraud_probability"] <= 1)
        self.assertEqual(value["is_fraud_prediction"], value["fraud_probability"] >= value["threshold"])
        self.assertEqual(len(value["top_factors"]), 5)
        self.assertTrue(all(math.isfinite(x["contribution"]) for x in value["top_factors"]))

    def test_missing_feature_does_not_emit_a_prediction(self):
        value = self.fixture()
        del value["amount"]
        result = self.invoke(value)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("Faltan variables", result.stderr)

    def test_infinite_amount_does_not_emit_a_prediction(self):
        value = self.fixture()
        value["amount"] = "Infinity"
        result = self.invoke(value)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("debe ser finita", result.stderr)

    def test_unseen_category_and_missing_numeric_are_supported(self):
        value = self.fixture()
        value["mcc"] = "UNKNOWN_CATEGORY"
        value["credit_score"] = None
        result = self.invoke(value)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
