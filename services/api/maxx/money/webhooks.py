"""PayPal webhook intake: verify the signature, store each event once, update the ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from maxx import schema, storage
from maxx.config import settings
from maxx.money import ledger

SIGNATURE_HEADER = "x-maxx-sim-signature"


def sign_simulated(body: bytes) -> str:
    return hmac.new(settings.simulator_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_simulated(headers: dict[str, str], body: bytes) -> bool:
    given = {k.lower(): v for k, v in headers.items()}.get(SIGNATURE_HEADER, "")
    return hmac.compare_digest(given, sign_simulated(body))


def _amount(resource: dict) -> Decimal | None:
    try:
        return Decimal(str(resource.get("amount", {}).get("value")))
    except (InvalidOperation, AttributeError):
        return None


def _apply(event_type: str, resource: dict) -> str:
    """Update the ledger from one verified event. Returns a short human summary."""
    resource_id = str(resource.get("id", ""))
    engine = storage.get_store().engine
    if event_type.startswith("BILLING.SUBSCRIPTION."):
        status = {
            "ACTIVATED": "ACTIVE",
            "CANCELLED": "CANCELLED",
            "SUSPENDED": "SUSPENDED",
            "EXPIRED": "EXPIRED",
        }.get(event_type.rsplit(".", 1)[1])
        if status:
            with engine.begin() as db:
                done = db.execute(
                    update(schema.subscriptions)
                    .where(schema.subscriptions.c.id == resource_id)
                    .values(status=status, updated_at=int(time.time()))
                )
            return f"subscription {status.lower()}" if done.rowcount else "unknown subscription"
        return "ignored"
    if event_type.startswith("PAYMENT.PAYOUTSBATCH."):
        batch = resource.get("batch_header", {}).get("payout_batch_id", resource_id)
        status = "SENT" if event_type.endswith("SUCCESS") else "FAILED"
        with engine.begin() as db:
            done = db.execute(
                update(schema.payouts)
                .where(schema.payouts.c.paypal_batch_id == batch)
                .values(status=status, updated_at=int(time.time()))
            )
        return f"payout {status.lower()}" if done.rowcount else "unknown payout"
    payment = ledger.by_resource(resource_id)
    if payment is None:
        return "unknown resource"
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        amount = _amount(resource)
        if amount is not None and amount > Decimal(payment["max_amount"]):
            return "capture above the hold; ignored"
        if payment["status"] in {"AUTHORIZED", "CAPTURE_FAILED"}:
            ledger.update_payment(
                payment["id"], status="CAPTURED", capture_id=resource_id, captured_amount=amount
            )
        return "capture confirmed"
    if event_type == "PAYMENT.CAPTURE.DENIED":
        if payment["status"] != "CAPTURED":
            ledger.update_payment(payment["id"], status="CAPTURE_FAILED", error="denied")
        return "capture denied"
    if event_type == "PAYMENT.CAPTURE.REFUNDED":
        ledger.update_payment(payment["id"], status="REFUNDED")
        return "capture refunded"
    if event_type == "PAYMENT.AUTHORIZATION.VOIDED":
        if payment["status"] in {"AUTHORIZED", "VOID_PENDING"}:
            ledger.update_payment(payment["id"], status="VOIDED", error="voided")
        return "hold released"
    return "ignored"


def handle_event(event: dict) -> dict:
    """Record and apply a verified event once. A redelivery is acknowledged, not redone."""
    event_id = str(event.get("id", ""))[:80]
    event_type = str(event.get("event_type", ""))[:80]
    if not event_id or not event_type:
        raise ValueError("Not a PayPal event.")
    resource = event.get("resource") or {}
    row = {
        "event_id": event_id,
        "event_type": event_type,
        "resource_id": str(resource.get("id", ""))[:80],
        "received_at": int(time.time()),
        "verified": True,
        "processed": False,
        "summary": "",
    }
    engine = storage.get_store().engine
    try:
        with engine.begin() as db:
            db.execute(schema.paypal_events.insert().values(**row))
    except IntegrityError:
        return {"duplicate": True}
    summary = _apply(event_type, resource)
    with engine.begin() as db:
        db.execute(
            update(schema.paypal_events)
            .where(schema.paypal_events.c.event_id == event_id)
            .values(processed=True, summary=summary[:300])
        )
    return {"duplicate": False, "summary": summary}


def recent_events(limit: int = 30) -> list[dict]:
    with storage.get_store().engine.connect() as db:
        rows = db.execute(
            select(schema.paypal_events)
            .order_by(schema.paypal_events.c.received_at.desc())
            .limit(limit)
        )
        return [dict(r._mapping) for r in rows]


def parse(body: bytes) -> dict:
    try:
        event = json.loads(body)
    except ValueError:
        raise ValueError("Not JSON.") from None
    if not isinstance(event, dict):
        raise ValueError("Not an event.")
    return event
