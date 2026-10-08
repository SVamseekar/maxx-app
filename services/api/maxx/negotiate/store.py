"""Transactional application snapshots, event journal and durable job state."""

from __future__ import annotations

import json
import time
import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError

from maxx import schema
from maxx.negotiate.contracts import Bloc, Event


class Conflict(Exception):
    pass


class BlocStore:
    def __init__(self, url: str, initialize=True):
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False}
            if url.startswith("sqlite:")
            else {"connect_timeout": 3},
            pool_pre_ping=True,
        )
        self.table, self.demands, self.jobs = schema.blocs, schema.demands, schema.jobs
        if initialize:
            schema.metadata.create_all(self.engine)

    def _events(self, db, bloc):
        last = (
            db.execute(
                select(func.max(schema.events.c.event_id)).where(
                    schema.events.c.bloc_id == bloc.id,
                    schema.events.c.generation == bloc.generation,
                )
            ).scalar()
            or 0
        )
        fresh = [e for e in bloc.events if e.id > last]
        if fresh:
            db.execute(
                schema.events.insert(),
                [
                    {
                        "bloc_id": bloc.id,
                        "generation": bloc.generation,
                        "event_id": e.id,
                        "document": e.model_dump_json(),
                    }
                    for e in fresh
                ],
            )

    def create(self, bloc: Bloc):
        try:
            with self.engine.begin() as db:
                db.execute(
                    self.table.insert().values(
                        id=bloc.id, revision=bloc.revision, document=bloc.model_dump_json()
                    )
                )
                self._events(db, bloc)
        except IntegrityError as exc:
            raise Conflict("Bloc already exists.") from exc

    def get(self, id: str) -> Bloc:
        with self.engine.connect() as db:
            row = db.execute(select(self.table.c.document).where(self.table.c.id == id)).first()
        if row is None:
            raise KeyError(id)
        return Bloc.model_validate_json(row[0])

    def list(self) -> list[Bloc]:
        with self.engine.connect() as db:
            return [
                Bloc.model_validate_json(r[0])
                for r in db.execute(select(self.table.c.document).order_by(self.table.c.id))
            ]

    def save(self, bloc: Bloc, queue=False):
        revision = bloc.revision + 1
        document = bloc.model_copy(update={"revision": revision}).model_dump_json()
        with self.engine.begin() as db:
            result = db.execute(
                self.table.update()
                .where(self.table.c.id == bloc.id, self.table.c.revision == bloc.revision)
                .values(revision=revision, document=document)
            )
            if result.rowcount != 1:
                raise Conflict("Bloc changed. Refresh and retry.")
            self._events(db, bloc)
            if queue:
                db.execute(
                    self.jobs.insert().values(
                        bloc_id=bloc.id, status="QUEUED", updated_at=int(time.time())
                    )
                )
            elif bloc.status in {"SETTLED", "FAILED"}:
                db.execute(
                    self.jobs.update()
                    .where(self.jobs.c.bloc_id == bloc.id)
                    .values(
                        status="SUCCEEDED" if bloc.status == "SETTLED" else "FAILED",
                        updated_at=int(time.time()),
                    )
                )
        bloc.revision = revision

    def job_status(self, id):
        with self.engine.connect() as db:
            return db.execute(select(self.jobs.c.status).where(self.jobs.c.bloc_id == id)).scalar()

    def queued_jobs(self):
        with self.engine.connect() as db:
            return list(
                db.execute(
                    select(self.jobs.c.bloc_id).where(self.jobs.c.status == "QUEUED")
                ).scalars()
            )

    def claim_job(self, id):
        with self.engine.begin() as db:
            return (
                db.execute(
                    self.jobs.update()
                    .where(self.jobs.c.bloc_id == id, self.jobs.c.status == "QUEUED")
                    .values(status="RUNNING", updated_at=int(time.time()))
                ).rowcount
                == 1
            )

    def replay(self, id, generation, after=0):
        with self.engine.connect() as db:
            return [
                Event.model_validate_json(r[0])
                for r in db.execute(
                    select(schema.events.c.document)
                    .where(
                        schema.events.c.bloc_id == id,
                        schema.events.c.generation == generation,
                        schema.events.c.event_id > after,
                    )
                    .order_by(schema.events.c.event_id)
                )
            ]

    def reset_demo(self, blocs: list[Bloc]):
        with self.engine.begin() as db:
            for bloc in blocs:
                db.execute(self.table.delete().where(self.table.c.id == bloc.id))
                db.execute(self.jobs.delete().where(self.jobs.c.bloc_id == bloc.id))
                db.execute(
                    self.table.insert().values(
                        id=bloc.id, revision=0, document=bloc.model_dump_json()
                    )
                )
                db.execute(schema.events.delete().where(schema.events.c.bloc_id == bloc.id))
                self._events(db, bloc)

    def record_demand(self, product_key, confidence, confirmed, mode):
        with self.engine.begin() as db:
            db.execute(
                self.demands.insert().values(
                    id=str(uuid.uuid4()),
                    document=json.dumps(
                        {
                            "product_key": product_key,
                            "confidence": confidence,
                            "confirmed": confirmed,
                            "mode": mode,
                        }
                    ),
                )
            )

    def demand_signals(self):
        with self.engine.connect() as db:
            return [json.loads(r[0]) for r in db.execute(select(self.demands.c.document))]

    def cache_get(self, key, now=None):
        with self.engine.connect() as db:
            row = db.execute(
                select(schema.cache.c.expires_at, schema.cache.c.document).where(
                    schema.cache.c.product_key == key
                )
            ).first()
        if row and row[0] > (int(time.time()) if now is None else now):
            return json.loads(row[1])
        return None

    def cache_put(self, key, document, now=None):
        # PostgreSQL upsert, SQLite supported only by isolated tests.
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        row = {
            "product_key": key,
            "expires_at": (int(time.time()) if now is None else now) + 21600,
            "document": json.dumps(document),
        }
        stmt = insert(schema.cache).values(**row)
        with self.engine.begin() as db:
            db.execute(stmt.on_conflict_do_update(index_elements=["product_key"], set_=row))

    def log_call(self, record):
        with self.engine.begin() as db:
            db.execute(
                schema.calls.insert().values(
                    id=str(uuid.uuid4()), created_at=time.time_ns(), metadata=json.dumps(record)
                )
            )

    def recent_calls(self):
        with self.engine.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    select(schema.calls.c.metadata)
                    .order_by(schema.calls.c.created_at.desc())
                    .limit(200)
                )
            ]

    def cache_expiry(self, key):
        with self.engine.connect() as db:
            return db.execute(
                select(schema.cache.c.expires_at).where(schema.cache.c.product_key == key)
            ).scalar()
