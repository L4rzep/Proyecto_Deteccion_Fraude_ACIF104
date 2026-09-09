"""Impide asociar una evaluación o explicación a un artefacto diferente."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseIdentityTest(unittest.TestCase):
    def test_evaluated_artifact_and_schema_are_the_served_artifacts(self):
        evaluation = json.loads((ROOT / "results/models/final_test_evaluation_metadata.json").read_text())
        schema_path = ROOT / "models/finan_feature_schema.json"
        model_path = ROOT / "models/finan_fraud_pipeline.joblib"
        metadata_path = ROOT / "results/models/final_model_training_metadata.json"
        for path, field in [(model_path, "pipeline_sha256"), (schema_path, "schema_sha256"),
                            (metadata_path, "training_metadata_sha256")]:
            payload = path.read_bytes()
            hashes = {hashlib.sha256(payload).hexdigest()}
            if path.suffix == ".json":
                # La evaluación se registró en Windows (CRLF); Git conserva LF.
                # Solo se permite esa diferencia, no cambios de contenido JSON.
                lf = payload.replace(b"\r\n", b"\n")
                hashes.add(hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest())
            self.assertIn(evaluation[field], hashes)
        schema = json.loads(schema_path.read_text())
        metrics = json.loads((ROOT / "results/models/final_test_metrics.json").read_text())
        self.assertEqual(schema["threshold"], metrics["threshold"])
        self.assertEqual(metrics["true_positives"] + metrics["false_negatives"], metrics["test_frauds"])
        self.assertTrue((ROOT / "results/models/final_test_evaluation.lock").is_file())
        shap = json.loads((ROOT / "results/shap/shap_metadata.json").read_text())
        self.assertEqual(shap["model_sha256"], evaluation["pipeline_sha256"])


if __name__ == "__main__":
    unittest.main()
