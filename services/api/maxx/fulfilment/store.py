"""Orders, delivery addresses and cases. Maxx coordinates fulfilment; the seller does it."""

from __future__ import annotations

import json
import re
import time
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from maxx import schema, secrets, storage

PURPOSE = "delivery-address"
OPEN_CASE = {"OPEN"}


def _engine():
    return storage.get_store().engine


def _row(row) -> dict | None:
    return dict(row._mapping) if row is not None else None


# ---- addresses ---------------------------------------------------------------------------------


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="", max_length=60)
    name: str = Field(min_length=2, max_length=100)
    line1: str = Field(min_length=3, max_length=200)
    line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str = Field(default="", max_length=100)
    postal: str = Field(min_length=2, max_length=20)
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    phone: str = Field(default="", max_length=30)

    @field_validator("country")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("phone")
    @classmethod
    def phone_shape(cls, value: str) -> str:
        if value and not re.fullmatch(r"[+()\d\s.-]{6,30}", value):
            raise ValueError("Enter a phone number with digits, spaces, + ( ) - only.")
        return value


def add_address(user_id: str, address: Address) -> dict:
    values = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "label": address.label,
        "country": address.country,
        "ciphertext": secrets.encrypt(address.model_dump_json(exclude={"label"}), PURPOSE),
        "created_at": int(time.time()),
        "deleted_at": None,
    }
    with _engine().begin() as db:
        db.execute(schema.delivery_addresses.insert().values(**values))
    return values


def summarize(address: dict) -> dict:
    """What the owner sees in a list: enough to recognise it, not the whole thing."""
    data = json.loads(secrets.decrypt(address["ciphertext"], PURPOSE))
    return {
        "id": address["id"],
        "label": address["label"],
        "name": data["name"],
        "line1": data["line1"],
        "city": data["city"],
        "postal": data["postal"],
        "country": data["country"],
    }


def list_addresses(user_id: str) -> list[dict]:
    with _engine().connect() as db:
        rows = db.execute(
            select(schema.delivery_addresses)
            .where(
                schema.delivery_addresses.c.user_id == user_id,
                schema.delivery_addresses.c.deleted_at.is_(None),
            )
            .order_by(schema.delivery_addresses.c.created_at.desc())
        )
        return [summarize(dict(r._mapping)) for r in rows]


def get_address(user_id: str, address_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.delivery_addresses).where(
                    schema.delivery_addresses.c.id == address_id,
                    schema.delivery_addresses.c.user_id == user_id,
                    schema.delivery_addresses.c.deleted_at.is_(None),
                )
            ).first()
        )


def delete_address(user_id: str, address_id: str) -> bool:
    with _engine().begin() as db:
        done = db.execute(
            update(schema.delivery_addresses)
            .where(
                schema.delivery_addresses.c.id == address_id,
                schema.delivery_addresses.c.user_id == user_id,
                schema.delivery_addresses.c.deleted_at.is_(None),
            )
            .values(deleted_at=int(time.time()), ciphertext="")
        )
    return done.rowcount == 1


def read_blob(blob: str | None) -> dict | None:
    if not blob:
        return None
    return json.loads(secrets.decrypt(blob, PURPOSE))


# ---- orders ------------------------------------------------------------------------------------


def create_order(
    payment_id: str,
    bloc_id: str,
    generation: int,
    buyer_id: str,
    seller_code: str,
    seller_user_id: str,
    title: str,
    amount: Decimal,
    currency: str,
    address_wait_until: int,
    simulated: bool = False,
) -> dict | None:
    """One order per captured payment. A second call for the same payment returns None."""
    stamp = int(time.time())
    values = {
        "simulated": simulated,
        "carrier_code": "",
        "tracker_id": None,
        "tracking_status": "",
        "tracking_detail": "",
        "review_flag": "",
        "id": str(uuid.uuid4()),
        "payment_id": payment_id,
        "bloc_id": bloc_id,
        "generation": generation,
        "buyer_id": buyer_id,
        "seller_code": seller_code,
        "seller_user_id": seller_user_id,
        "title": title,
        "amount": amount,
        "currency": currency,
        "status": "AWAITING_ADDRESS",
        "ship_by": address_wait_until,  # until an address arrives, this is the address deadline
        "carrier": "",
        "tracking": "",
        "address_blob": None,
        "address_country": "",
        "created_at": stamp,
        "updated_at": stamp,
    }
    try:
        with _engine().begin() as db:
            db.execute(schema.orders.insert().values(**values))
    except IntegrityError:
        return None
    return values


def get_order(order_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(db.execute(select(schema.orders).where(schema.orders.c.id == order_id)).first())


def order_for_payment(payment_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.orders).where(schema.orders.c.payment_id == payment_id)
            ).first()
        )


def update_order(order_id: str, expect: set[str] | None = None, **fields) -> bool:
    """Change an order, optionally only from certain states (a guard against double actions)."""
    fields["updated_at"] = int(time.time())
    condition = schema.orders.c.id == order_id
    if expect:
        condition = condition & schema.orders.c.status.in_(sorted(expect))
    with _engine().begin() as db:
        return db.execute(update(schema.orders).where(condition).values(**fields)).rowcount == 1


def orders_where(**filters) -> list[dict]:
    query = select(schema.orders).order_by(schema.orders.c.created_at.desc())
    for key, value in filters.items():
        query = query.where(getattr(schema.orders.c, key) == value)
    with _engine().connect() as db:
        return [dict(r._mapping) for r in db.execute(query)]


def orders_in(statuses: list[str]) -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(select(schema.orders).where(schema.orders.c.status.in_(statuses)))
        ]


# ---- cases -------------------------------------------------------------------------------------


def open_case_for(order_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.cases).where(
                    schema.cases.c.order_id == order_id, schema.cases.c.status == "OPEN"
                )
            ).first()
        )


def get_case(case_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(db.execute(select(schema.cases).where(schema.cases.c.id == case_id)).first())


def create_case(order_id: str, opened_by: str, kind: str, message: str, respond_hours: int) -> dict:
    stamp = int(time.time())
    case = {
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "opened_by": opened_by,
        "kind": kind,
        "status": "OPEN",
        "opened_at": stamp,
        "respond_by": stamp + respond_hours * 3600,
        "resolved_at": None,
        "resolution": "",
    }
    with _engine().begin() as db:
        db.execute(schema.cases.insert().values(**case))
    add_event(case["id"], "buyer", message)
    return case


def add_event(case_id: str, actor: str, body: str) -> None:
    with _engine().begin() as db:
        db.execute(
            schema.case_events.insert().values(
                id=str(uuid.uuid4()),
                case_id=case_id,
                actor=actor,
                body=body[:2000],
                created_at=int(time.time()),
            )
        )


def events_for(case_id: str) -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.case_events)
                .where(schema.case_events.c.case_id == case_id)
                .order_by(schema.case_events.c.created_at)
            )
        ]


def close_case(case_id: str, status: str, resolution: str) -> bool:
    with _engine().begin() as db:
        done = db.execute(
            update(schema.cases)
            .where(schema.cases.c.id == case_id, schema.cases.c.status == "OPEN")
            .values(status=status, resolved_at=int(time.time()), resolution=resolution[:500])
        )
    return done.rowcount == 1


def cases_for_orders(order_ids: list[str]) -> list[dict]:
    if not order_ids:
        return []
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.cases)
                .where(schema.cases.c.order_id.in_(order_ids))
                .order_by(schema.cases.c.opened_at.desc())
            )
        ]


def all_open_cases() -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.cases)
                .where(schema.cases.c.status == "OPEN")
                .order_by(schema.cases.c.opened_at)
            )
        ]


# ---- seller adjustments (money a seller owes after a refund) -------------------------------------


def add_adjustment(seller_code: str, order_id: str, amount: Decimal, reason: str) -> None:
    with _engine().begin() as db:
        db.execute(
            schema.seller_adjustments.insert().values(
                id=str(uuid.uuid4()),
                seller_code=seller_code,
                order_id=order_id,
                amount=amount,
                reason=reason[:200],
                created_at=int(time.time()),
            )
        )


def take_adjustments(seller_code: str, available: Decimal) -> Decimal:
    """Deduct what a seller owes from a payout. Returns how much was taken (never more than
    `available`); partly covered debts shrink instead of disappearing."""
    taken = Decimal(0)
    with _engine().begin() as db:
        rows = db.execute(
            select(schema.seller_adjustments)
            .where(
                schema.seller_adjustments.c.seller_code == seller_code,
                schema.seller_adjustments.c.settled_at.is_(None),
            )
            .order_by(schema.seller_adjustments.c.created_at)
        ).all()
        for row in rows:
            room = available - taken
            if room <= 0:
                break
            owed = Decimal(row.amount)
            if owed <= room:
                taken += owed
                db.execute(
                    update(schema.seller_adjustments)
                    .where(schema.seller_adjustments.c.id == row.id)
                    .values(settled_at=int(time.time()))
                )
            else:
                taken += room
                db.execute(
                    update(schema.seller_adjustments)
                    .where(schema.seller_adjustments.c.id == row.id)
                    .values(amount=owed - room)
                )
    return taken


def owed_by(seller_code: str) -> Decimal:
    with _engine().connect() as db:
        rows = db.execute(
            select(schema.seller_adjustments.c.amount).where(
                schema.seller_adjustments.c.seller_code == seller_code,
                schema.seller_adjustments.c.settled_at.is_(None),
            )
        ).scalars()
        return sum((Decimal(a) for a in rows), Decimal(0))
