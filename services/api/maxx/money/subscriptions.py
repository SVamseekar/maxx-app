"""Maxx Plus: a PayPal subscription. Status changes only through verified webhook events."""

from __future__ import annotations

import time
import uuid

from sqlalchemy import select

from maxx import schema, storage
from maxx.config import settings
from maxx.money import webhooks
from maxx.money.paypal import get_paypal

PLANS = {
    "weekly": {"label": "Weekly", "price": "6.99", "interval": "week"},
    "yearly": {"label": "Yearly", "price": "49.00", "interval": "year"},
}


def _engine():
    return storage.get_store().engine


def current(user_id: str) -> dict | None:
    with _engine().connect() as db:
        row = db.execute(
            select(schema.subscriptions)
            .where(schema.subscriptions.c.user_id == user_id)
            .order_by(schema.subscriptions.c.created_at.desc())
        ).first()
    return dict(row._mapping) if row else None


def is_premium(user_id: str) -> bool:
    found = current(user_id)
    return bool(found and found["status"] == "ACTIVE")


def checkout_limit(user_id: str) -> str:
    return (
        settings.checkout_premium_max_amount
        if is_premium(user_id)
        else settings.checkout_max_amount
    )


def plan_id(plan: str) -> str:
    return settings.paypal_plan_weekly if plan == "weekly" else settings.paypal_plan_yearly


async def subscribe(user_id: str, plan: str) -> dict:
    pp = get_paypal()
    if pp is None:
        raise ValueError("Payments are turned off.")
    existing = current(user_id)
    if existing and existing["status"] == "ACTIVE":
        raise ValueError("You already have Maxx Plus.")
    if not pp.simulated and not plan_id(plan):
        raise ValueError("This plan is not set up on the server yet.")
    base = settings.public_base_url.rstrip("/")
    sub = await pp.create_subscription(
        plan_id(plan) or f"SIMULATED-{plan}",
        request_id=f"sub-{uuid.uuid4()}",
        return_url=f"{base}/account?plus=thanks",
        cancel_url=f"{base}/account?plus=cancelled",
    )
    stamp = int(time.time())
    with _engine().begin() as db:
        db.execute(
            schema.subscriptions.insert().values(
                id=sub["id"],
                user_id=user_id,
                plan=plan,
                status="APPROVAL_PENDING",
                simulated=pp.simulated,
                created_at=stamp,
                updated_at=stamp,
            )
        )
    return {"id": sub["id"], "approve_url": sub["approve_url"], "simulated": pp.simulated}


def deliver_simulated(subscription_id: str, kind: str) -> dict:
    """The simulator's PayPal sends the same event a real one would, through the same handler."""
    event = {
        "id": f"WH-SIM-{uuid.uuid4().hex[:16]}",
        "event_type": f"BILLING.SUBSCRIPTION.{kind}",
        "resource": {"id": subscription_id},
    }
    return webhooks.handle_event(event)


async def cancel(user_id: str) -> None:
    pp = get_paypal()
    found = current(user_id)
    if pp is None or not found or found["status"] != "ACTIVE":
        raise ValueError("There is no active subscription to cancel.")
    await pp.cancel_subscription(found["id"], "Cancelled by the subscriber")
    if pp.simulated:
        deliver_simulated(found["id"], "CANCELLED")
