"""Seller accounts and standing offers, and how they join a Bloc."""

from __future__ import annotations

import secrets
import time
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from maxx import schema, storage
from maxx.negotiate.blocs import emit
from maxx.negotiate.contracts import Bloc, Seller

STRATEGIES = {
    # (per-round concession, instruction for a language-model seller)
    "firm": (Decimal("0.02"), "Hold your price. Concede slowly and only against clear volume."),
    "balanced": (Decimal("0.05"), "Concede steadily over the rounds without selling below floor."),
    "eager": (Decimal("0.09"), "Prefer volume and a quick sale. Concede fast, never below floor."),
}
MAX_REAL_SELLERS = 8


def _engine():
    return storage.get_store().engine


def _row(row) -> dict | None:
    return dict(row._mapping) if row is not None else None


def by_user(user_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(select(schema.sellers).where(schema.sellers.c.user_id == user_id)).first()
        )


def by_id(seller_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(select(schema.sellers).where(schema.sellers.c.id == seller_id)).first()
        )


def by_identity_session(session_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.sellers).where(schema.sellers.c.identity_session == session_id)
            ).first()
        )


def by_code(code: str) -> dict | None:
    with _engine().connect() as db:
        return _row(db.execute(select(schema.sellers).where(schema.sellers.c.code == code)).first())


def create(user_id: str, profile: dict) -> dict:
    """Create the seller record from a validated profile. Starts PENDING until the payout email
    is confirmed (and, when SELLER_REVIEW=manual, until an administrator approves)."""
    stamp = int(time.time())
    for _ in range(5):
        values = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "code": "S" + secrets.token_hex(3).upper(),
            "payout_verified": False,
            "status": "PENDING",
            "terms_accepted_at": stamp,
            "certified_at": stamp,
            "created_at": stamp,
            "updated_at": stamp,
            "strikes": 0,
            **profile,
        }
        try:
            with _engine().begin() as db:
                db.execute(schema.sellers.insert().values(**values))
            return by_user(user_id)
        except IntegrityError:
            if by_user(user_id):
                raise
    raise RuntimeError("Could not allocate a seller code.")


def update_seller(seller_id: str, **fields) -> None:
    fields["updated_at"] = int(time.time())
    with _engine().begin() as db:
        db.execute(update(schema.sellers).where(schema.sellers.c.id == seller_id).values(**fields))


def offers_for(seller_id: str) -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.seller_offers)
                .where(schema.seller_offers.c.seller_id == seller_id)
                .order_by(schema.seller_offers.c.created_at.desc())
            )
        ]


def get_offer(seller_id: str, offer_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.seller_offers).where(
                    schema.seller_offers.c.id == offer_id,
                    schema.seller_offers.c.seller_id == seller_id,
                )
            ).first()
        )


def upsert_offer(
    seller_id: str,
    product_key: str,
    title: str,
    stock: int,
    floor: Decimal,
    opening: Decimal,
    strategy: str,
    agent: str = "rules",
    guidance: str = "",
    listing: dict | None = None,
) -> dict:
    """Create or replace the seller's standing offer for a product. `listing` (gtin, category,
    typical_price) marks an offer the seller published before any buyer asked."""
    stamp = int(time.time())
    with _engine().begin() as db:
        existing = db.execute(
            select(schema.seller_offers.c.id).where(
                schema.seller_offers.c.seller_id == seller_id,
                schema.seller_offers.c.product_key == product_key,
            )
        ).scalar()
        values = {
            "title": title,
            "stock": stock,
            "floor": floor,
            "opening_price": opening,
            "strategy": strategy,
            "agent": agent,
            "guidance": guidance,
            "active": True,
            "updated_at": stamp,
        }
        if listing is not None:
            values.update(
                listing=True,
                gtin=listing.get("gtin") or "",
                category=listing["category"],
                typical_price=listing["typical_price"],
            )
        if existing:
            db.execute(
                update(schema.seller_offers)
                .where(schema.seller_offers.c.id == existing)
                .values(**values)
            )
            offer_id = existing
        else:
            offer_id = str(uuid.uuid4())
            db.execute(
                schema.seller_offers.insert().values(
                    id=offer_id,
                    seller_id=seller_id,
                    product_key=product_key,
                    created_at=stamp,
                    **values,
                )
            )
    return get_offer(seller_id, offer_id)


def set_active(seller_id: str, offer_id: str, active: bool) -> bool:
    with _engine().begin() as db:
        done = db.execute(
            update(schema.seller_offers)
            .where(
                schema.seller_offers.c.id == offer_id,
                schema.seller_offers.c.seller_id == seller_id,
            )
            .values(active=active, updated_at=int(time.time()))
        )
    return done.rowcount == 1


def count_listings(seller_id: str) -> int:
    with _engine().connect() as db:
        return len(
            db.execute(
                select(schema.seller_offers.c.id).where(
                    schema.seller_offers.c.seller_id == seller_id,
                    schema.seller_offers.c.listing.is_(True),
                    schema.seller_offers.c.active.is_(True),
                )
            ).all()
        )


def offer_by_id(offer_id: str) -> dict | None:
    with _engine().connect() as db:
        return _row(
            db.execute(
                select(schema.seller_offers).where(schema.seller_offers.c.id == offer_id)
            ).first()
        )


def listings() -> list[dict]:
    with _engine().connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(
                select(schema.seller_offers, schema.sellers.c.code, schema.sellers.c.business_name)
                .join(schema.sellers, schema.sellers.c.id == schema.seller_offers.c.seller_id)
                .where(schema.seller_offers.c.listing.is_(True))
                .order_by(schema.seller_offers.c.created_at.desc())
                .limit(200)
            )
        ]


def attach(bloc: Bloc) -> int:
    """Add every verified seller with an active standing offer for this product to the Bloc.

    Their floor, stock and opening price are theirs. The agent that negotiates for them is bounded
    by the same clamps as every other seller: never below the floor, never beyond stock.
    """
    from maxx.sellers import lifecycle

    s, o = schema.sellers.c, schema.seller_offers.c
    with _engine().connect() as db:
        rows = db.execute(
            select(schema.sellers, schema.seller_offers)
            .join(schema.seller_offers, o.seller_id == s.id)
            .where(
                o.product_key == bloc.product_key,
                o.active.is_(True),
                s.status == "ACTIVE",
                s.payout_verified.is_(True),
            )
            .order_by(o.created_at)
            .limit(MAX_REAL_SELLERS)
        ).all()
    taken = {seller.id for seller in bloc.sellers}
    added = 0
    for row in rows:
        data = row._mapping
        if data["code"] in taken or Decimal(data["floor"]) > Decimal(bloc.typical_price) * 2:
            continue
        if bool(data["demo"]) != (bloc.origin == "demo_tour"):
            continue  # demo sellers sell only in their own tour; real sellers never in one
        if not lifecycle.can_sell(by_code(data["code"])):
            continue  # a compliance deadline or re-certification is overdue
        concession, style = STRATEGIES[data["strategy"]]
        bloc.sellers.append(
            Seller(
                id=data["code"],
                floor=Decimal(data["floor"]),
                opening_price=Decimal(data["opening_price"]),
                stock=int(data["stock"]),
                style=style,
                account_id=data["user_id"],
                concession=concession,
                agent=data["agent"] if data["agent"] in {"rules", "ai"} else "rules",
                guidance=data["guidance"] or "",
            )
        )
        added += 1
    if added:
        emit(bloc, "sellers_registered", count=added)
    return added


def public_profile(seller: dict) -> dict:
    """What a buyer who bought from this seller is entitled to see (EU DSA art. 30 trader info)."""
    return {
        "code": seller["code"],
        "business_name": seller["business_name"],
        "legal_name": seller["legal_name"],
        "business_type": seller["business_type"],
        "address": ", ".join(
            part
            for part in (
                seller["address_line1"],
                seller["address_city"],
                seller["address_region"],
                seller["address_postal"],
                seller["country"],
            )
            if part
        ),
        "phone": seller["phone"],
        "support_email": seller["support_email"],
        "website": seller["website"],
        "trade_register_no": seller["trade_register_no"],
        "ship_within_days": seller["ship_within_days"],
        "return_days": seller["return_days"],
        "return_policy": seller["return_policy"],
        "self_certified": bool(seller["certified_at"]),
    }


def payout_receiver(code: str) -> str | None:
    """Where a real seller's money goes, or None while their account cannot be paid."""
    seller = by_code(code)
    if seller and seller["status"] == "ACTIVE" and seller["payout_verified"]:
        return seller["payout_email"]
    return None


def mask_email(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}{'•' * max(1, min(len(name) - 1, 6))}@{domain}"
