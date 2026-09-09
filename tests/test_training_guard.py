"""Una reproducción no puede sobrescribir el modelo que ya fue evaluado."""
import subprocess
import sys
import unittest
from pathlib import Path

class TrainingGuardTest(unittest.TestCase):
    def test_existing_release_is_rejected_before_database_access(self):
        root=Path(__file__).resolve().parents[1]
        p=subprocess.run([sys.executable, str(root/'src/models/07_train_final_model.py')],
                         capture_output=True,text=True,timeout=10)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('Se conservan los artefactos existentes',p.stderr)
        self.assertNotIn('pyodbc',p.stderr)

if __name__=='__main__':unittest.main()
