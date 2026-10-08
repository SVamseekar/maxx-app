"""Actual Postgres transaction/restart/cache/job/replay probe in a temporary schema."""

import asyncio
import json
import uuid
from decimal import Decimal

from sqlalchemy import text

from maxx import schema
from maxx.config import settings
from maxx.negotiate.blocs import add_member, make_bloc, transition
from maxx.negotiate.routes import Runtime
from maxx.negotiate.store import BlocStore


def main():
    name = "maxx_verify_" + uuid.uuid4().hex
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise SystemExit("Postgres DATABASE_URL required.")
    first = BlocStore(settings.database_url, initialize=False)
    try:
        with first.engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{name}"'))
        first.engine = first.engine.execution_options(schema_translate_map={None: name})
        schema.metadata.create_all(first.engine)
        b = make_bloc("probe", "Headphones", Decimal("200"))
        add_member(b, "you", "150")
        first.create(b)
        transition(b, "NEGOTIATING")
        first.save(b, queue=True)
        first.cache_put("probe", [{"price": "150"}], now=100)
        first.log_call({"provider": "probe", "status": "fixture", "tokens": None, "latency_ms": 0})
        reopened = BlocStore(settings.database_url, initialize=False)
        reopened.engine = reopened.engine.execution_options(schema_translate_map={None: name})
        runtime = Runtime(reopened, delay=0)
        runtime.recover()
        assert reopened.job_status(b.id) == "QUEUED"

        async def finish():
            await runtime.tick()
            await asyncio.gather(*runtime.tasks.values())

        asyncio.run(finish())
        final = reopened.get(b.id)
        assert final.status == "SETTLED" and reopened.job_status(b.id) == "SUCCEEDED"
        assert reopened.replay(b.id, b.generation) == final.events
        assert (
            reopened.cache_get("probe", now=21699)
            and reopened.cache_get("probe", now=21700) is None
        )
        assert reopened.recent_calls()[0]["provider"] == "probe"
        interrupted = make_bloc("interrupted", "Headphones", Decimal("200"))
        add_member(interrupted, "you", "150")
        reopened.create(interrupted)
        transition(interrupted, "NEGOTIATING")
        reopened.save(interrupted, queue=True)
        assert reopened.claim_job(interrupted.id) and not reopened.claim_job(interrupted.id)
        Runtime(reopened).recover()
        assert reopened.get(interrupted.id).members[0].status == "RELEASED"
        assert reopened.job_status(interrupted.id) == "FAILED"
        reopened.engine.dispose()
        print(
            json.dumps(
                {
                    "status": "verified",
                    "database": "postgres",
                    "queued_job_restart": "passed",
                    "running_job_recovery": "passed",
                    "event_replay": "passed",
                    "cache_expiry": "passed",
                    "metadata_restart": "passed",
                }
            )
        )
    finally:
        with first.engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        first.engine.dispose()


if __name__ == "__main__":
    main()
