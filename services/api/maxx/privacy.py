"""Access, portability and erasure: what a person can take with them or have removed.

Some records must be kept after an account is deleted (payments, and seller trader details for a
period after the relationship ends). Those keep an opaque account id and nothing else about the
person; everything else is deleted. The privacy page says exactly this.
"""

from __future__ import annotations

import time

from sqlalchemy import select, update

from maxx import audit, schema, storage
from maxx.auth import store as accounts
from maxx.fulfilment import store as fulfilment
from maxx.money import ledger
from maxx.sellers import store as sellers

OPEN_ORDER = {"AWAITING_ADDRESS", "AWAITING_SHIPMENT", "SHIPPED"}


def blockers(user_id: str) -> list[str]:
    """Reasons an account cannot be closed right now. Empty means it can."""
    reasons = []
    if any(o["status"] in OPEN_ORDER for o in fulfilment.orders_where(buyer_id=user_id)):
        reasons.append("You have an order that has not been delivered yet.")
    if any(fulfilment.open_case_for(o["id"]) for o in fulfilment.orders_where(buyer_id=user_id)):
        reasons.append("You have an open problem report.")
    seller = sellers.by_user(user_id)
    if seller:
        mine = fulfilment.orders_where(seller_user_id=user_id)
        if any(o["status"] in {"AWAITING_SHIPMENT", "AWAITING_ADDRESS"} for o in mine):
            reasons.append("You have orders waiting to be shipped. Ship or wait for the refund.")
        if any(fulfilment.open_case_for(o["id"]) for o in mine):
            reasons.append("A buyer has an open problem with one of your orders.")
        if fulfilment.owed_by(seller["code"]) > 0:
            reasons.append("You owe Maxx money from refunded orders.")
    return reasons


def export(user_id: str) -> dict:
    """Everything Maxx holds about this account in a portable form (GDPR art. 15 and 20)."""
    user = accounts.get_user(user_id)
    if user is None:
        return {}
    addresses = []
    with storage.get_store().engine.connect() as db:
        for row in db.execute(
            select(schema.delivery_addresses).where(
                schema.delivery_addresses.c.user_id == user_id,
                schema.delivery_addresses.c.deleted_at.is_(None),
            )
        ):
            data = fulfilment.read_blob(row.ciphertext) or {}
            addresses.append({"label": row.label, **data})
    orders = fulfilment.orders_where(buyer_id=user_id)
    cases = fulfilment.cases_for_orders([o["id"] for o in orders])
    seller = sellers.by_user(user_id)
    return {
        "exported_at": int(time.time()),
        "account": {
            "id": user.id,
            "email": user.email,
            "email_verified": user.email_verified,
            "display_name": user.display_name,
            "created_at": user.created_at,
            "two_step_enabled": user.totp_enabled,
            "sign_in_providers": accounts.list_identities(user.id),
        },
        "security_activity": [
            {
                "kind": e.kind,
                "at": e.created_at,
                "network": e.ip_prefix,
                "browser": e.user_agent,
                "detail": e.detail,
            }
            for e in accounts.list_events(user.id, 500)
        ],
        "delivery_addresses": addresses,
        "payments": [
            {
                "kind": p["kind"],
                "status": p["status"],
                "amount_held_or_paid": str(p["captured_amount"] or p["max_amount"]),
                "currency": p["currency"],
                "paypal_order": p["order_id"],
                "paypal_capture": p["capture_id"],
                "at": p["updated_at"],
                "simulated": bool(p["simulated"]),
            }
            for p in ledger.for_user(user.id)
        ],
        "orders": [
            {
                "id": o["id"],
                "title": o["title"],
                "amount": str(o["amount"]),
                "status": o["status"],
                "seller": o["seller_code"],
                "tracking": o["tracking"],
                "created_at": o["created_at"],
            }
            for o in orders
        ],
        "problem_reports": [
            {
                "id": c["id"],
                "order": c["order_id"],
                "kind": c["kind"],
                "status": c["status"],
                "messages": [
                    {"from": e["actor"], "text": e["body"], "at": e["created_at"]}
                    for e in fulfilment.events_for(c["id"])
                ],
            }
            for c in cases
        ],
        "seller_profile": {
            k: seller[k]
            for k in (
                "code business_name legal_name business_type country address_line1 address_city "
                "address_region address_postal phone support_email website trade_register_no "
                "payout_email ship_within_days ships_to return_days return_policy status"
            ).split()
        }
        if seller
        else None,
        "seller_offers": [
            {
                "title": o["title"],
                "stock": o["stock"],
                "floor": str(o["floor"]),
                "opening_price": str(o["opening_price"]),
                "strategy": o["strategy"],
            }
            for o in (sellers.offers_for(seller["id"]) if seller else [])
        ],
    }


def erase(user_id: str) -> None:
    """Remove personal data tied to commerce. Called after `blockers` is empty and holds are voided.

    Addresses are deleted, the address copies on finished orders are wiped, offers are removed, and
    a seller record is closed but kept (trader details have a retention period)."""
    now = int(time.time())
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.delivery_addresses)
            .where(schema.delivery_addresses.c.user_id == user_id)
            .values(deleted_at=now, ciphertext="")
        )
        db.execute(
            update(schema.orders)
            .where(schema.orders.c.buyer_id == user_id)
            .values(address_blob=None)
        )
    seller = sellers.by_user(user_id)
    if seller:
        with storage.get_store().engine.begin() as db:
            db.execute(
                schema.seller_offers.delete().where(
                    schema.seller_offers.c.seller_id == seller["id"]
                )
            )
        sellers.update_seller(
            seller["id"], status="CLOSED", payout_verified=False, payout_email="closed"
        )
    audit.record("system", "account.erased", user_id[:8], "commerce data removed")
