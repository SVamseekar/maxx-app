"""Measured HTTP scan evaluation. Fixture consistency is never model accuracy."""

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import httpx2 as httpx

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:3001/api/scan")
parser.add_argument("--repeats", type=int, default=3)
parser.add_argument("--output", default=str(ROOT / "latest-results.json"))
args = parser.parse_args()
cases = json.loads((ROOT / "fixtures.json").read_text())
records = []
fields = ["title", "price", "currency", "merchant", "qty"]
with httpx.Client(timeout=115) as client:
    for case in cases:
        for repeat in range(args.repeats):
            started = time.perf_counter()
            response = client.post(
                args.url,
                content=(ROOT / case["file"]).read_bytes(),
                headers={"Content-Type": "image/png"},
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            data = response.json()
            records.append(
                {
                    "case": case["name"],
                    "repeat": repeat,
                    "http_status": response.status_code,
                    "elapsed_ms": elapsed,
                    "mode": data.get("mode"),
                    "field_matches": sum(
                        data.get("item", {}).get(f) == case["item"].get(f)
                        for f in fields
                    ),
                    "field_count": len(fields),
                    "score": data.get("score", {}).get("value"),
                    "provider_calls": len(data.get("calls", [])),
                }
            )
latencies = sorted(r["elapsed_ms"] for r in records)
modes = sorted({r["mode"] or "error" for r in records})
report = {
    "modes": modes,
    "runs": len(records),
    "successful": sum(r["http_status"] == 200 for r in records),
    "screenshots": len(cases),
    "p50_ms": statistics.median(latencies),
    "p90_ms": latencies[math.ceil(len(latencies) * 0.9) - 1],
    "measurement": "wall-clock HTTP upload through Next.js proxy to FastAPI",
    "field_exact_match": sum(r["field_matches"] for r in records)
    / sum(r["field_count"] for r in records),
    "interpretation": "Fixture replay consistency only; model accuracy and live provider latency unmeasured."
    if modes == ["fixture"]
    else "Small synthetic sample; not the planned 40-image benchmark.",
    "records": records,
}
Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))
