"""One-way, idempotent import of legacy local SQLite snapshots; sources untouched."""

import argparse
import hashlib
import json
import sqlite3
import time

from sqlalchemy.dialects.postgresql import insert

from maxx import schema, storage
from maxx.config import ROOT
from maxx.negotiate.blocs import make_bloc
from maxx.negotiate.contracts import Bloc
from maxx.negotiate.store import Conflict
from maxx.providers import token_counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store = storage.get_store()
    counts = {"blocs": 0, "calls": 0, "demands": 0}
    for name in ("blocs.sqlite", "model_calls.sqlite"):
        path = ROOT / ".local" / name
        if not path.exists():
            continue
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "bloc_documents" in tables:
                for (raw,) in db.execute("SELECT document FROM bloc_documents"):
                    b = Bloc.model_validate_json(raw)
                    template = make_bloc(
                        b.id, b.title, b.typical_price, mode=b.mode, scenario=b.scenario
                    )
                    if not b.closes_at:
                        b.closes_at = template.closes_at
                    if b.market_mode == "unavailable":
                        b.target_price = None
                    for seller, persona in zip(b.sellers, template.sellers, strict=False):
                        seller.style = persona.style
                    counts["blocs"] += 1
                    if args.apply:
                        try:
                            store.create(b)
                        except Conflict:
                            pass
            if "demand_signals" in tables:
                for id, raw in db.execute("SELECT id, document FROM demand_signals"):
                    counts["demands"] += 1
                    if args.apply:
                        with store.engine.begin() as target:
                            target.execute(
                                insert(schema.demands)
                                .values(id=id, document=raw)
                                .on_conflict_do_nothing()
                            )
            if "model_calls" in tables:
                for id, raw in db.execute("SELECT id, metadata FROM model_calls"):
                    record = json.loads(raw)
                    record = {
                        k: v
                        for k, v in record.items()
                        if k
                        in (
                            "request_id",
                            "provider",
                            "purpose",
                            "model",
                            "status",
                            "tokens",
                            "cost_usd",
                            "latency_ms",
                        )
                    }
                    record["tokens"] = token_counts(record.get("tokens"))
                    counts["calls"] += 1
                    if args.apply:
                        key = "legacy-" + hashlib.sha256(f"{name}:{id}".encode()).hexdigest()
                        with store.engine.begin() as target:
                            target.execute(
                                insert(schema.calls)
                                .values(
                                    id=key, created_at=time.time_ns(), metadata=json.dumps(record)
                                )
                                .on_conflict_do_nothing()
                            )
    print(
        json.dumps(
            {
                "mode": "applied" if args.apply else "dry-run",
                "source_untouched": True,
                "legacy_records": counts,
            }
        )
    )


if __name__ == "__main__":
    main()
