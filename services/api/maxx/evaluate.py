"""Repeatable local/live HTTP evaluation; never treats replay as model accuracy."""

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx2 as httpx

from maxx.config import ROOT
from maxx.evaluation import invariant_violations, matching_metrics
from maxx.matching import CATALOG
from maxx.negotiate.adapters import Bid, safe_offer
from maxx.negotiate.contracts import Member, Seller
from maxx.negotiate.engine import clear


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--base", default="http://127.0.0.1:3001/api")
    parser.add_argument("--output")
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()
    report = {
        "provider_mode": args.mode,
        "seed": args.seed,
        "interpretation": "Fixture replay/rule consistency; no model accuracy claim."
        if args.mode == "fixture"
        else "Live synthetic pilot; not a representative 40-image benchmark.",
    }
    output = Path(args.output) if args.output else ROOT / f"evals/core-{args.mode}.json"
    rng = random.Random(args.seed)
    try:
        with httpx.Client(timeout=115) as client:
            config = client.get(args.base + "/transparency")
            config.raise_for_status()
            modes = config.json()["modes"]
            if any(modes[k] != args.mode for k in ("scan", "matching", "negotiation")):
                raise ValueError(f"Provider mode mismatch: expected {args.mode}, observed {modes}")
            cases = json.loads((ROOT / "evals/fixtures.json").read_text())
            fields = ["title", "price", "currency", "merchant", "qty"]
            scans = []
            for case in cases:
                start = time.perf_counter()
                response = client.post(
                    args.base + "/scan",
                    content=(ROOT / "evals" / case["file"]).read_bytes(),
                    headers={"Content-Type": "image/png"},
                )
                response.raise_for_status()
                data = response.json()
                if data["mode"] != args.mode:
                    raise ValueError("Scan mode changed during evaluation")
                scans.append(
                    {
                        "case": case["name"],
                        "mode": data["mode"],
                        "field_matches": sum(
                            data["item"].get(f) == case["item"].get(f) for f in fields
                        ),
                        "fields": len(fields),
                        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                        "provider_calls": len(data["calls"]),
                    }
                )
            # 50 exact identities + 10 ambiguous/contradictory/out-of-catalogue cases.
            pairs = [
                (
                    {"title": p.title, "brand": p.brand, "model": p.model, "variant": p.variant},
                    p.product_key,
                )
                for p in CATALOG
            ]
            pairs += [({"title": p.title.rsplit(" ", 1)[0]}, None) for p in CATALOG[::10]]
            pairs += [
                ({"title": "Sony WH-1000XM5", "variant": v}, None) for v in ("Red", "Blue", "White")
            ]
            pairs += [({"title": "Unrecognised lamp"}, None), ({"title": "Sony headphones"}, None)]
            matches = []
            for item, expected in pairs:
                response = client.post(args.base + "/catalog/match", json=item)
                response.raise_for_status()
                data = response.json()
                if data["mode"] != args.mode:
                    raise ValueError("Matching mode changed during evaluation")
                matches.append(
                    {
                        "item": item,
                        "expected": expected,
                        "actual": data["candidates"][0]["product_key"]
                        if data["candidates"]
                        else None,
                        "requires_confirmation": data["requires_confirmation"],
                        "mode": data["mode"],
                    }
                )
        report["extraction"] = {
            "screenshots": len(scans),
            "fields": sum(r["fields"] for r in scans),
            "exact_field_accuracy": sum(r["field_matches"] for r in scans)
            / sum(r["fields"] for r in scans),
            "p50_ms": statistics.median(r["latency_ms"] for r in scans),
            "records": scans,
        }
        report["matching"] = {
            "pairs": len(matches),
            **matching_metrics(
                [r["expected"] for r in matches],
                [(r["actual"], r["requires_confirmation"]) for r in matches],
            ),
            "records": matches,
        }
        violations = []
        partial = 0
        for index in range(200):
            members = [
                Member(
                    id=str(i),
                    user_id=str(i),
                    max_price=Decimal(rng.randint(1, 50000)) / 100,
                    joined_order=i,
                )
                for i in range(rng.randint(1, 80))
            ]
            sellers = [
                Seller(
                    id=str(i),
                    floor=Decimal(rng.randint(1, 50000)) / 100,
                    opening_price="500",
                    stock=rng.randint(0, 20),
                )
                for i in range(rng.randint(1, 8))
            ]
            offers = [
                safe_offer(
                    s, Bid(price=Decimal(rng.randint(1, 50000)) / 100, max_qty=rng.randint(0, 30))
                )[0]
                for s in sellers
            ]
            result = clear(members, offers)
            errors = invariant_violations(members, sellers, result)
            if result != clear(list(reversed(members)), list(reversed(offers))):
                errors.append("nondeterministic")
            if errors:
                violations.append({"case": index, "violations": errors})
            partial += bool(result.allocations and result.unserved)
        report["negotiation_invariants"] = {
            "mode": "local deterministic engine; no provider calls",
            "random_blocs": 200,
            "partial_allocation_cases": partial,
            "violation_count": sum(len(r["violations"]) for r in violations),
            "violations": violations,
        }
        # Actual local/provider runner over HTTP/SSE, separate from randomized pure-engine cases.
        negotiation_file = output.with_name(output.stem + "-negotiations.json")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "evals/run_negotiations.py"),
                "--base",
                args.base,
                "--output",
                str(negotiation_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        negotiations = json.loads(negotiation_file.read_text())
        if any(r["mode"] != args.mode for r in negotiations["records"]):
            raise ValueError("Negotiation mode changed during evaluation")
        report["streamed_negotiations"] = negotiations
        report["status"] = "passed" if not violations else "failed"
    except (httpx.HTTPError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        report["status"] = "unverified"
        report["reason"] = "Evaluation incomplete; check modes, API and server-side credentials."
        report["error_type"] = type(exc).__name__
        if isinstance(exc, subprocess.CalledProcessError):
            lines = (exc.stderr or exc.stdout or "").strip().splitlines()
            report["detail"] = lines[-1][:300] if lines else ""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    summary = {
        k: (
            {x: y for x, y in v.items() if x != "records"} if k in ("extraction", "matching") else v
        )
        for k, v in report.items()
    }
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "streamed_negotiations"},
            indent=2,
        )
    )
    if report["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
