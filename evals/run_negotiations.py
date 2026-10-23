"""Real HTTP/SSE smoke evaluation of three scenarios. Labels actual provider mode."""

import argparse
import json
import time
from pathlib import Path

import httpx2 as httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="http://127.0.0.1:3001/api")
parser.add_argument("--output", default="evals/negotiation-results.json")
parser.add_argument("--email", help="Existing account (an administrator when ADMIN_EMAILS is set)")
parser.add_argument("--password", help="Password for --email")
args = parser.parse_args()
records = []
with httpx.Client(timeout=120) as client:
    # Joining and resetting need an account. Without --email a throwaway one is created.
    # Accounts are created by emailed link, so a script signs in to one made beforehand:
    #   make dev-account EMAIL=eval@example.com PASSWORD='a long passphrase'
    if not args.email:
        raise SystemExit("Pass --email and --password for an account (see `make dev-account`).")
    credentials = {"email": args.email, "password": args.password or ""}
    client.post(args.base + "/auth/login", json=credentials).raise_for_status()
    reset_started = time.perf_counter()
    response = client.post(args.base + "/demo/reset", json={})
    response.raise_for_status()
    reset_ms = round((time.perf_counter()-reset_started)*1000, 2)
    for scenario in ["success", "failure", "flaky"]:
        id = "demo-" + scenario
        client.post(
            f"{args.base}/blocs/{id}/join",
            json={"max_price": "150"},
        ).raise_for_status()
        before = client.get(f"{args.base}/blocs/{id}").json()
        cursor = before["events"][-1]["id"]
        started = time.perf_counter()
        client.post(f"{args.base}/blocs/{id}/start", json={}).raise_for_status()
        ids, events, first_event_ms = [], [], None
        with client.stream(
            "GET", f"{args.base}/blocs/{id}/stream?after={cursor}"
        ) as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    if first_event_ms is None:
                        first_event_ms = round(
                            (time.perf_counter() - started) * 1000, 2
                        )
                    event = json.loads(line[6:])
                    ids.append(event["id"])
                    events.append(event["type"])
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result = client.get(f"{args.base}/blocs/{id}").json()
        assert result["status"] in ["SETTLED", "FAILED"]
        assert ids == sorted(set(ids)), "Duplicate/out-of-order streamed events"
        assert all(m["status"] != "HELD" for m in result["members"])
        for m in result["members"]:
            if m["status"] == "WIN":
                from decimal import Decimal

                assert Decimal(m["final_price"]) <= Decimal(m["max_price"])
        if result["mode"] == "fixture":
            assert result["status"] == (
                "FAILED" if scenario == "failure" else "SETTLED"
            )
            if scenario == "flaky":
                assert "seller_withdrew" in events
                assert all(
                    a["seller_id"] != "A" for a in result["outcome"]["allocations"]
                )
        records.append(
            {
                "scenario": scenario,
                "mode": result["mode"],
                "status": result["status"],
                "rounds": result["round"],
                "elapsed_ms": elapsed,
                "first_event_ms": first_event_ms,
                "streamed_events": len(events),
                "provider_calls": len(result["calls"]),
                "allocated": len(result["outcome"]["allocations"]),
                "unserved": len(result["outcome"]["unserved"]),
            }
        )
report = {
    "reset_ms": reset_ms,
    "measurement": "HTTP through Next.js proxy with incrementally consumed SSE",
    "interpretation": "Fixture mode measures local plumbing only; live quality/cost unverified unless separately evaluated.",
    "records": records,
}
Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
