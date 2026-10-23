"""Payments ledger: one row per PayPal order/authorization, so every dollar is traceable."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

from sqlalchemy import select, update

from maxx import schema, storage

TERMINAL_HOLD = {"CAPTURED", "VOIDED", "FAILED", "EXPIRED"}


def _engine():
    return storage.get_store().engine


def _row(row) -> dict | None:
    return dict(row._mapping) if row is not None else None


def new_payment(
    kind: str,
    order_id: str,
    max_amount: Decimal,
    simulated: bool,
    user_id: str | None = None,
    bloc_id: str | None = None,
    generation: int = 0,
    meta: str = "",
    currency: str = "USD",
) -> dict:
    stamp = int(time.time())
    values = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "bloc_id": bloc_id,
        "generation": generation,
        "member_id": None,
        "user_id": user_id,
        "order_id": order_id,
        "authorization_id": None,
        "capture_id": None,
        "max_amount": max_amount,
        "captured_amount": None,
        "currency": currency,
        "status": "CREATED",
        "simulated": simulated,
        "error": "",
        "meta": meta,
        "created_at": stamp,
        "updated_at": stamp,
    }
    with _engine().begin() as db:
        db.execute(schema.payments.insert().values(**values))
    return values


def get(payment_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(select(schema.payments).where(schema.payments.c.id == payment_id)).first()
        )


def by_order(order_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.payments).where(schema.payments.c.order_id == order_id)
            ).first()
        )


def by_resource(resource_id: str) -> dict | None:
    """Find a payment from any PayPal id it carries (order, authorization or capture)."""
    table = schema.payments.c
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.payments).where(
                    (table.order_id == resource_id)
                    | (table.authorization_id == resource_id)
                    | (table.capture_id == resource_id)
                )
            ).first()
        )


def update_payment(payment_id: str, **fields) -> None:
    fields["updated_at"] = int(time.time())
    with _engine().begin() as db:
        db.execute(
            update(schema.payments).where(schema.payments.c.id == payment_id).values(**fields)
        )


def for_bloc(bloc_id: str, generation: int | None = None) -> list[dict]:
    query = select(schema.payments).where(schema.payments.c.bloc_id == bloc_id)
    if generation is not None:
        query = query.where(schema.payments.c.generation == generation)
    with _engine().connect() as db:
        return [dict(r._mapping) for r in db.execute(query.order_by(schema.payments.c.created_at))]


def for_user(user_id: str) -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.payments)
                .where(schema.payments.c.user_id == user_id)
                .order_by(schema.payments.c.created_at.desc())
            )
        ]


def active_hold(bloc_id: str, generation: int, user_id: str) -> dict | None:
    table = schema.payments.c
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.payments).where(
                    table.kind == "hold",
                    table.bloc_id == bloc_id,
                    table.generation == generation,
                    table.user_id == user_id,
                    table.status.in_(["CREATED", "APPROVED", "AUTHORIZED"]),
                )
            ).first()
        )


def open_pyusd_units() -> set[int]:
    """Exact amounts promised to orders still waiting for payment, so tags never collide."""
    import json

    with _engine().connect() as db:
        rows = db.execute(
            select(schema.payments.c.meta).where(
                schema.payments.c.kind == "checkout",
                schema.payments.c.status.in_(["CREATED", "APPROVED"]),
                schema.payments.c.order_id.like("PYUSD-%"),
            )
        ).scalars()
        units = set()
        for meta in rows:
            try:
                units.add(int(json.loads(meta)["units"]))
            except (ValueError, KeyError, TypeError):
                continue
        return units
