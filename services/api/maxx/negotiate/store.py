"""Transactional application snapshots, event journal and durable job state."""

from __future__ import annotations

import json
import time
import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError

from maxx import schema
from maxx.config import settings
from maxx.negotiate.contracts import Bloc, Event


class Conflict(Exception):
    pass


class BlocStore:
    def __init__(self, url: str, initialize=True):
        sqlite = url.startswith("sqlite:")
        pool = (
            {}
            if sqlite
            else {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_recycle": settings.db_pool_recycle,
            }
        )
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if sqlite else {"connect_timeout": 3},
            pool_pre_ping=True,
            **pool,
        )
        self.table, self.demands, self.jobs = schema.blocs, schema.demands, schema.jobs
        if initialize:
            schema.metadata.create_all(self.engine)

    @staticmethod
    def _index(bloc: Bloc) -> dict:
        """The columns kept beside the document. Real accounts only in `participants`."""
        users = sorted({m.user_id for m in bloc.members if not m.user_id.startswith("seed-")})
        return {
            "generation": bloc.generation,
            "status": bloc.status,
            "product_key": bloc.product_key[:300],
            "closes_at": bloc.closes_at or 0,
            "owner_id": bloc.owner_id,
            "title": bloc.title[:300],
            "typical_price": bloc.typical_price,
            "target_price": bloc.target_price,
            "mode": bloc.mode,
            "scenario": bloc.scenario,
            "buyers": sum(m.status != "LEFT" for m in bloc.members),
            "committed": sum((m.max_price for m in bloc.members if m.status == "HELD"), 0),
            "participants": "|" + "|".join(users) + "|" if users else "",
            "seller_codes": "|" + "|".join(s.id for s in bloc.sellers) + "|"
            if bloc.sellers
            else "",
        }

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
                        id=bloc.id,
                        revision=bloc.revision,
                        document=bloc.model_dump_json(),
                        **self._index(bloc),
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

    # ---- cheap reads: never parse a document ------------------------------------------------

    def meta(self, id: str) -> dict | None:
        """Revision, generation and status in one tiny query (polling, ETags, SSE)."""
        t = self.table.c
        with self.engine.connect() as db:
            row = db.execute(select(t.revision, t.generation, t.status).where(t.id == id)).first()
        return dict(row._mapping) if row else None

    def generations(self) -> dict[str, int]:
        with self.engine.connect() as db:
            return {
                r[0]: r[1] for r in db.execute(select(self.table.c.id, self.table.c.generation))
            }

    def summaries(self, viewer_id: str | None = None, status: str | None = None) -> list[dict]:
        t = self.table.c
        query = select(
            t.id,
            t.title,
            t.status,
            t.scenario,
            t.mode,
            t.target_price,
            t.typical_price,
            t.committed,
            t.buyers,
            t.closes_at,
            t.owner_id,
            t.participants,
            t.product_key,
        ).order_by(t.id)
        if status:
            query = query.where(t.status == status)
        # A seller tour Bloc or a judge's scenario copy is private: reachable by its link only.
        query = query.where(~t.product_key.startswith("demo-tour:"))
        query = query.where(~t.product_key.startswith("demo-lab:"))  # a judge's private copy
        with self.engine.connect() as db:
            rows = [dict(r._mapping) for r in db.execute(query)]
        for row in rows:
            row["viewer_is_owner"] = bool(viewer_id and row["owner_id"] == viewer_id)
            row["viewer_joined"] = bool(viewer_id and f"|{viewer_id}|" in row["participants"])
            del row["participants"], row["owner_id"]
        return rows

    def _docs(self, *conditions) -> list[Bloc]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(self.table.c.document).where(*conditions).order_by(self.table.c.id)
            )
            return [Bloc.model_validate_json(r[0]) for r in rows]

    def list_by_status(self, statuses: list[str]) -> list[Bloc]:
        return self._docs(self.table.c.status.in_(statuses))

    def list_open(self) -> list[Bloc]:
        return self._docs(self.table.c.status == "OPEN")

    def find_by_product(self, product_key: str) -> Bloc | None:
        found = self._docs(self.table.c.product_key == product_key)
        return found[0] if found else None

    def list_with_seller(self, code: str) -> list[Bloc]:
        return self._docs(self.table.c.seller_codes.like(f"%|{code}|%"))

    def list_for_user(self, user_id: str) -> list[Bloc]:
        t = self.table.c
        return self._docs((t.owner_id == user_id) | t.participants.like(f"%|{user_id}|%"))

    def due_to_close(self, now: int) -> list[str]:
        t = self.table.c
        with self.engine.connect() as db:
            return list(
                db.execute(
                    select(t.id).where(t.status == "OPEN", t.closes_at > 0, t.closes_at <= now)
                ).scalars()
            )

    def latest_event(self, id: str, generation: int) -> int:
        with self.engine.connect() as db:
            return (
                db.execute(
                    select(func.max(schema.events.c.event_id)).where(
                        schema.events.c.bloc_id == id, schema.events.c.generation == generation
                    )
                ).scalar()
                or 0
            )

    def save(self, bloc: Bloc, queue=False):
        revision = bloc.revision + 1
        document = bloc.model_copy(update={"revision": revision}).model_dump_json()
        with self.engine.begin() as db:
            result = db.execute(
                self.table.update()
                .where(self.table.c.id == bloc.id, self.table.c.revision == bloc.revision)
                .values(revision=revision, document=document, **self._index(bloc))
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
                        id=bloc.id,
                        revision=0,
                        document=bloc.model_dump_json(),
                        **self._index(bloc),
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
