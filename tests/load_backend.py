"""Mide procesos de inferencia con SHAP. Entradas sintéticas; excluye SQL, WinForms y datos S9."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_one(_):
    start = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, str(ROOT / "src/inference/predict_transaction.py"),
                            "--input-json", str(ROOT / "tests/fixtures/transaccion_sintetica.json"),
                            "--explain"], capture_output=True, text=True, timeout=60, cwd=ROOT)
        valid = p.returncode == 0 and json.loads(p.stdout).get("status") == "ok"
        return {"seconds": time.perf_counter()-start, "ok": valid, "timeout": False}
    except subprocess.TimeoutExpired:
        return {"seconds": time.perf_counter()-start, "ok": False, "timeout": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=12)
    args = parser.parse_args()
    if args.output.exists() or args.requests < 10:
        raise ValueError("Use una salida nueva y al menos 10 solicitudes por nivel.")
    records = []
    for concurrency in (1, 2, 4):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(executor.map(run_one, range(args.requests)))
        elapsed = time.perf_counter()-start
        times = sorted(x["seconds"] for x in results)
        p95 = times[max(0, int(.95*len(times)+.999999)-1)]
        records.append({"concurrency": concurrency, "requests": len(results),
                        "errors": sum(not x["ok"] for x in results),
                        "timeouts": sum(x["timeout"] for x in results),
                        "p50_seconds": statistics.median(times), "p95_seconds": p95,
                        "elapsed_seconds": elapsed, "throughput_requests_per_second": len(results)/elapsed,
                        "proposed_p95_15s_met": p95 <= 15, "measurements": results})
        print(f"Concurrencia {concurrency}: p95={p95:.3f}s, errores={records[-1]['errors']}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scope": "synthetic_python_process_with_shap_only", "date_utc": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "platform": platform.platform(), "python": platform.python_version(),
        "includes_process_startup_and_model_loading": True, "sql_and_winforms_tested": False,
        "availability_not_measured": True, "proposed_p95_limit_seconds": 15,
        "model_sha256": hashlib.sha256((ROOT / 'models/finan_fraud_pipeline.joblib').read_bytes()).hexdigest(),
        "results": records}, indent=2)+'\n')
