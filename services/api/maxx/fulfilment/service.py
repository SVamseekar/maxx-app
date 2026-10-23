"""Marketplace rules between a captured payment and a happy buyer.

Maxx does not ship, inspect or insure goods; the seller does. Maxx coordinates, and protects the
buyer's money until the carrier confirms the seller really shipped:

  captured -> order awaits a delivery address -> awaits shipment -> shipped -> delivered
  no address in time, or not shipped in time, or buyer cancels before shipping -> full refund
  problem after shipping -> a case; the seller replies; Maxx rules if they disagree

When the seller is paid depends on the carrier and on the seller's record (TRACKING_MODE on):
  an established seller (PAYOUT_TRUSTED_AFTER_DELIVERIES delivered orders, no strikes) is paid
  once the carrier has scanned the parcel; a newer seller once it is delivered. A tracking number
  must be well-formed for its carrier (check digit included), may not be reused for another
  buyer's order, and a parcel that is returned, lost or never scanned holds the payout for a
  person. With tracking off, sellers are paid when they mark the order shipped, as before.

Orders won from the simulated sellers are fulfilled by a clearly labelled automatic stand-in, so
a buyer's journey completes in the demo exactly as it would with a real seller.

Every state change is guarded (only from the expected state) and written to the audit log.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from maxx import audit, schema, storage
from maxx.config import settings
from maxx.fulfilment import store, tracking, tracking_numbers
from maxx.money import ledger
from maxx.money.paypal import CENTS, PAYOUT_DONE, PAYOUT_FAILED, PayPalError, get_paypal
from maxx.negotiate.contracts import Bloc
from maxx.notify.service import notify, safe_text
from maxx.sellers import store as sellers

log = logging.getLogger(__name__)
DAY = 86400
CASE_KINDS = {"not_received", "not_as_described", "return_request", "other"}
SIMULATED_USER = "simulated"
SIMULATED_NAMES = {
    "A": "Volume Wholesale",
    "B": "Premium Retail",
    "C": "Stock Clearance",
    "D": "Small Boutique",
    "E": "Competitive Resale",
    "F": "Patient Distribution",
    "G": "Seasonal Outlet",
    "H": "Careful Supply",
}


class Refused(ValueError):
    """A rule said no. The message is safe to show the person."""


# A person reviewed a flagged shipment and released it; the flag text keeps their note.
CLEARED = "Cleared by Maxx: "


def flagged(order: dict) -> bool:
    """A delivery problem is waiting for a person."""
    return bool(order["review_flag"]) and not order["review_flag"].startswith(CLEARED)


def _fee(gross: Decimal) -> Decimal:
    return (gross * Decimal(settings.platform_fee_percent) / 100).quantize(CENTS)


def _date(stamp: int | None) -> str:
    if not stamp:
        return "soon"
    return datetime.fromtimestamp(stamp, UTC).strftime("%d %b %Y, %H:%M UTC")


def simulated_profile(code: str) -> dict:
    """Trader details for a simulated seller, labelled so nobody mistakes it for a business."""
    name = SIMULATED_NAMES.get(code, "Demo seller")
    return {
        "code": code,
        "business_name": f"{name} (simulated seller)",
        "legal_name": "Not a real business: an automatic stand-in in the Maxx demo",
        "business_type": "company",
        "address": "None. Nothing is shipped; tracking is simulated.",
        "phone": "",
        "support_email": "",
        "website": "",
        "trade_register_no": "",
        "ship_within_days": 1,
        "return_days": 30,
        "return_policy": "The simulated seller refunds any problem report automatically.",
        "self_certified": False,
        "simulated": True,
    }


# ---- creation ----------------------------------------------------------------------------------


def create_orders(bloc: Bloc) -> int:
    """After a Bloc settles, give every real buyer who won an order, whoever the seller is."""
    made = 0
    members = {m.id: m for m in bloc.members}
    by_id = {s.id: s for s in bloc.sellers}
    for payment in ledger.for_bloc(bloc.id, bloc.generation):
        if payment["kind"] != "hold" or payment["status"] != "CAPTURED":
            continue
        member = members.get(payment["member_id"] or "")
        seller = by_id.get(member.seller_id or "") if member else None
        if member is None or seller is None:
            continue
        simulated = seller.account_id is None
        order = store.create_order(
            payment["id"],
            bloc.id,
            bloc.generation,
            payment["user_id"],
            seller.id,
            seller.account_id or SIMULATED_USER,
            bloc.title,
            Decimal(payment["captured_amount"]),
            payment["currency"],
            int(time.time()) + settings.address_wait_days * DAY,
            simulated=simulated,
        )
        if not order:
            continue
        made += 1
        audit.record("system", "order.created", order["id"], f"{bloc.id} seller {seller.id}")
        title = safe_text(bloc.title)
        notify(
            payment["user_id"],
            "order.won",
            f"You won {title} for ${order['amount']}",
            "Add a delivery address so the seller can ship it. If you do not by "
            f"{_date(order['ship_by'])}, the order is cancelled and refunded in full.",
            "/orders",
            f"won:{order['id']}",
        )
        if not simulated:
            notify(
                seller.account_id,
                "seller.order_new",
                f"New order: {title}",
                f"A buyer won one unit at ${order['amount']}. You will be told when they give "
                "a delivery address; then you ship it.",
                "/sell",
                f"order-new:{order['id']}",
            )
    return made


# ---- buyer: address ----------------------------------------------------------------------------


def set_address(buyer_id: str, order_id: str, address_id: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != buyer_id:
        raise LookupError("Order not found.")
    if order["status"] not in {"AWAITING_ADDRESS", "AWAITING_SHIPMENT"}:
        raise Refused("This order has already shipped or closed, so its address is locked.")
    address = store.get_address(buyer_id, address_id)
    if not address:
        raise LookupError("Address not found.")
    seller = None if order["simulated"] else sellers.by_code(order["seller_code"])
    fields: dict = {"address_blob": address["ciphertext"], "address_country": address["country"]}
    if seller and seller["ships_to"] and address["country"] not in seller["ships_to"].split(","):
        raise Refused(
            "This seller does not ship to that country. Choose another address or cancel."
        )
    first = order["status"] == "AWAITING_ADDRESS"
    if first:
        days = seller["ship_within_days"] if seller else 1
        fields.update(status="AWAITING_SHIPMENT", ship_by=int(time.time()) + days * DAY)
    store.update_order(order_id, {"AWAITING_ADDRESS", "AWAITING_SHIPMENT"}, **fields)
    audit.record(f"user:{buyer_id[:8]}", "order.address", order_id)
    fresh = store.get_order(order_id)
    if first and seller:
        notify(
            seller["user_id"],
            "seller.order_ready",
            f"Ship {safe_text(order['title'])} by {_date(fresh['ship_by'])}",
            "The buyer gave a delivery address. Ship with tracking and enter the tracking "
            "number in your seller console.",
            "/sell",
            f"order-ready:{order_id}",
        )
    return fresh


# ---- seller: ship ------------------------------------------------------------------------------


def check_tracking(order: dict, carrier: str, number: str) -> tuple[str, bool]:
    """Validate a tracking number for an order. Returns (normalised number, recognised format).

    Refuses an unknown carrier, a number that does not fit the carrier's format or check digit,
    and a number already used for a different buyer's order (sellers combining several of the
    same buyer's orders in one parcel may reuse it).
    """
    if carrier not in tracking_numbers.CARRIERS:
        raise Refused("Choose the carrier from the list.")
    number = tracking_numbers.normalise(number)
    if not 3 <= len(number) <= 64 or not number.isalnum():
        raise Refused("Enter the tracking number exactly as the carrier gave it.")
    test_code = tracking.is_test_code(number) and settings.tracking_mode == "simulator"
    recognised = test_code or (
        carrier != "other" and tracking_numbers.recognise(carrier, number) is not None
    )
    if carrier != "other" and not recognised:
        label = tracking_numbers.CARRIERS[carrier]["label"]
        raise Refused(
            f"That is not a valid {label} tracking number (its format or check digit is wrong). "
            "Check it against the label."
        )
    with storage.get_store().engine.connect() as db:
        clash = db.execute(
            select(schema.orders.c.buyer_id, schema.orders.c.seller_code).where(
                schema.orders.c.tracking == number,
                schema.orders.c.id != order["id"],
            )
        ).all()
    if any(
        row.buyer_id != order["buyer_id"] or row.seller_code != order["seller_code"]
        for row in clash
    ):
        raise Refused("That tracking number is already used for another order.")
    return number, bool(recognised)


async def ship(seller_user_id: str, order_id: str, carrier: str, number: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["seller_user_id"] != seller_user_id:
        raise LookupError("Order not found.")
    if order["status"] == "AWAITING_ADDRESS":
        raise Refused("The buyer has not given a delivery address yet.")
    if order["status"] != "AWAITING_SHIPMENT":
        raise Refused("This order can no longer be marked as shipped.")
    number, _ = check_tracking(order, carrier, number)
    tracker_id = None
    if tracking.enabled():
        try:
            tracker_id = await tracking.register(carrier, number, order["address_country"])
        except tracking.TrackingError as exc:
            raise Refused(f"{exc} Nothing changed; try again shortly.") from None
    label = tracking_numbers.CARRIERS[carrier]["label"]
    if not store.update_order(
        order_id,
        {"AWAITING_SHIPMENT"},
        status="SHIPPED",
        carrier=label,
        carrier_code=carrier,
        tracking=number,
        tracker_id=tracker_id,
        tracking_status="pre_transit" if tracker_id else "",
        shipped_at=int(time.time()),
    ):
        raise Refused("This order changed. Refresh and try again.")
    actor = "simulated-seller" if order["simulated"] else f"seller:{order['seller_code']}"
    audit.record(actor, "order.shipped", order_id, f"{carrier} {number[-6:]}")
    await _share_tracking_with_paypal(order, carrier, number)
    notify(
        order["buyer_id"],
        "order.shipped",
        f"{safe_text(order['title'])} has shipped",
        f"Carrier: {label}. Tracking number: {number}. Follow it on your orders page.",
        "/orders",
        f"shipped:{order_id}",
    )
    if tracker_id:
        await refresh_tracking(store.get_order(order_id))
    await release_payout(order_id)
    return store.get_order(order_id)


async def _share_tracking_with_paypal(order: dict, carrier: str, number: str) -> None:
    """Best effort: a failure here never blocks shipping."""
    pp = get_paypal()
    payment = ledger.get(order["payment_id"])
    if pp is None or not payment or not payment.get("capture_id"):
        return
    try:
        await pp.add_tracking(
            payment["order_id"],
            payment["capture_id"],
            number,
            carrier.upper(),
            request_id=f"track-{order['id']}",
        )
    except PayPalError as exc:
        audit.record("system", "paypal.tracking_failed", order["id"], exc.name[:60])


# ---- carrier updates ---------------------------------------------------------------------------


def _store_events(order_id: str, events: list[dict]) -> int:
    with storage.get_store().engine.connect() as db:
        seen = {
            (row.status, row.at)
            for row in db.execute(
                select(schema.tracking_events.c.status, schema.tracking_events.c.at).where(
                    schema.tracking_events.c.order_id == order_id
                )
            )
        }
    fresh = [e for e in events if (e["status"], int(e["at"])) not in seen]
    if fresh:
        with storage.get_store().engine.begin() as db:
            for event in fresh:
                db.execute(
                    schema.tracking_events.insert().values(
                        id=str(uuid.uuid4()),
                        order_id=order_id,
                        status=event["status"][:30],
                        message=event["message"][:200],
                        location=event["location"][:120],
                        at=int(event["at"]),
                    )
                )
    return len(fresh)


def tracking_history(order_id: str) -> list[dict]:
    with storage.get_store().engine.connect() as db:
        return [
            {
                "status": row.status,
                "message": row.message,
                "location": row.location,
                "at": row.at,
            }
            for row in db.execute(
                select(schema.tracking_events)
                .where(schema.tracking_events.c.order_id == order_id)
                .order_by(schema.tracking_events.c.at)
            )
        ]


async def refresh_tracking(order: dict | None) -> str | None:
    """Re-read the carrier's view of a shipped order and act on it. Returns the status."""
    if not order or not order["tracker_id"] or order["status"] not in {"SHIPPED", "DELIVERED"}:
        return None
    try:
        state = await tracking.fetch(order["tracker_id"])
    except tracking.TrackingError as exc:
        log.info("Tracking refresh for %s failed: %s", order["id"], exc)
        return None
    _store_events(order["id"], state.events)
    now = int(time.time())
    fields: dict = {
        "tracking_status": state.status,
        "tracking_detail": state.detail,
        "tracking_checked_at": now,
        "estimated_delivery": state.estimated_delivery,
    }
    if state.status in tracking.SCANNED and not order["first_scan_at"]:
        scans = [e["at"] for e in state.events if e["status"] in tracking.SCANNED]
        fields["first_scan_at"] = min(scans) if scans else now
    flag = order["review_flag"]
    if (
        state.destination_country
        and order["address_country"]
        and state.destination_country != order["address_country"]
        and not flag
    ):
        flag = "The carrier's destination country differs from the buyer's address."
    if state.status in tracking.TROUBLE and not flag:
        flag = f"The carrier reports: {state.status.replace('_', ' ')}."
    fields["review_flag"] = flag
    store.update_order(order["id"], None, **fields)
    title = safe_text(order["title"])
    if flag and flag != order["review_flag"]:
        audit.record("system", "order.flagged", order["id"], flag[:120])
        notify(
            order["buyer_id"],
            "order.tracking_issue",
            f"A problem with the delivery of {title}",
            "The carrier reports a problem with this parcel. The seller has not been paid. "
            "If it does not arrive, report a problem on your orders page for a full refund.",
            "/orders",
            f"track-issue-buyer:{order['id']}",
        )
        if not order["simulated"]:
            notify(
                order["seller_user_id"],
                "seller.tracking_issue",
                f"Delivery problem: {title}",
                "The carrier reports a problem with this parcel, so the payout is on hold until "
                "Maxx reviews it. Contact the carrier and reply in your seller console.",
                "/sell",
                f"track-issue-seller:{order['id']}",
            )
    if state.status == "out_for_delivery" and order["tracking_status"] != "out_for_delivery":
        notify(
            order["buyer_id"],
            "order.out_for_delivery",
            f"{title} is out for delivery",
            "The carrier expects to deliver it today.",
            "/orders",
            f"ofd:{order['id']}",
        )
    if state.status == "delivered" and order["status"] == "SHIPPED":
        if store.update_order(order["id"], {"SHIPPED"}, status="DELIVERED", delivered_at=now):
            audit.record("carrier", "order.delivered", order["id"])
            notify(
                order["buyer_id"],
                "order.delivered",
                f"{title} was delivered",
                "The carrier confirms delivery. If anything is wrong, report a problem within "
                "60 days of your order.",
                "/orders",
                f"delivered:{order['id']}",
            )
    await release_payout(order["id"])
    return state.status


# ---- payouts -----------------------------------------------------------------------------------


def _payout_for_order(order_id: str) -> dict | None:
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.payouts).where(schema.payouts.c.order_id == order_id)
        ).first()
    return dict(row._mapping) if row else None


def deliveries_by(seller_code: str) -> int:
    with storage.get_store().engine.connect() as db:
        return int(
            db.execute(
                select(func.count()).where(
                    schema.orders.c.seller_code == seller_code,
                    schema.orders.c.status == "DELIVERED",
                )
            ).scalar()
            or 0
        )


def trusted(seller: dict | None, seller_code: str) -> bool:
    """Established sellers are paid at the first carrier scan instead of on delivery."""
    if seller is None:
        return False
    return (
        int(seller["strikes"]) == 0
        and deliveries_by(seller_code) >= settings.payout_trusted_after_deliveries
    )


def payout_gate(order: dict, seller: dict | None) -> str | None:
    """Why this shipped order's payout must wait, or None if it can be paid now."""
    if flagged(order):
        return "under_review"
    if order["review_flag"].startswith(CLEARED) or order["status"] == "DELIVERED":
        return None
    if not tracking.enabled():
        # No carrier feed: a well-formed number for a known carrier is paid on shipping; an
        # "other carrier" parcel waits for delivery to be confirmed.
        return "awaiting_delivery" if order["carrier_code"] == "other" else None
    if not order["tracker_id"]:
        return "awaiting_delivery"
    if not order["first_scan_at"]:
        return "awaiting_carrier"
    return None if trusted(seller, order["seller_code"]) else "awaiting_delivery"


def _receiver(order: dict, seller: dict | None) -> str | None:
    if order["simulated"]:
        return settings.paypal_seller_receiver
    if seller and seller["status"] == "ACTIVE" and seller["payout_verified"]:
        return seller["payout_email"]
    return None


async def release_payout(order_id: str) -> str:
    """Pay the seller for a shipped order, once. Returns SENT, FAILED, WAITING, OFFSET or NONE."""
    order = store.get_order(order_id)
    pp = get_paypal()
    if pp is None or not order or order["status"] not in {"SHIPPED", "DELIVERED"}:
        return "NONE"
    existing = _payout_for_order(order_id)
    if existing and existing["status"] in {"SENT", "OFFSET", "FAILED"}:
        return existing["status"]
    if store.open_case_for(order_id) or audit.payments_frozen():
        return "WAITING"  # a dispute or the emergency brake pauses the money
    seller = None if order["simulated"] else sellers.by_code(order["seller_code"])
    receiver = _receiver(order, seller)
    if receiver is None:
        return "WAITING"
    if seller is not None:
        cooldown = settings.payout_cooldown_hours * 3600
        if seller["payout_verified_at"] and time.time() < seller["payout_verified_at"] + cooldown:
            return "WAITING"  # a newly confirmed address is not paid immediately
    if payout_gate(order, seller):
        return "WAITING"
    gross = Decimal(order["amount"])
    fee = _fee(gross)
    stamp = int(time.time())
    if existing is None:
        net = gross - fee
        taken = (
            Decimal(0) if order["simulated"] else store.take_adjustments(order["seller_code"], net)
        )
        net -= taken
        row = {
            "id": str(uuid.uuid4()),
            "bloc_id": order["bloc_id"],
            "generation": order["generation"],
            "seller_id": order["seller_code"],
            "method": "paypal",
            "gross_amount": gross,
            "fee_amount": fee,
            "net_amount": net,
            "units": 1,
            "sender_batch_id": f"maxx-order-{order_id}",
            "paypal_batch_id": None,
            "receiver": receiver,
            "status": "OFFSET" if net <= 0 else "PENDING",
            "tx_hash": None,
            "simulated": pp.simulated,
            "created_at": stamp,
            "updated_at": stamp,
            "order_id": order_id,
            "item_status": "",
            "attempt": 1,
            "failure_reason": "",
        }
        try:
            with storage.get_store().engine.begin() as db:
                db.execute(schema.payouts.insert().values(**row))
        except IntegrityError:
            row = _payout_for_order(order_id)
        if row["status"] == "OFFSET":
            audit.record("system", "payout.offset", order_id, f"owed {taken}")
            return "OFFSET"
    else:
        row = existing
    return await _send(pp, order, row)


async def _send(pp, order: dict, row: dict) -> str:
    batch_id = row["sender_batch_id"]
    try:
        batch = await pp.create_payout(
            batch_id,
            [
                {
                    "receiver": row["receiver"],
                    "amount": row["net_amount"],
                    "sender_item_id": f"order-{order['id']}-{row['attempt']}"[:63],
                    "note": f"Maxx order {safe_text(order['title'], 60)}",
                }
            ],
        )
        status, paypal_id, reason = "SENT", batch["batch_id"], ""
    except PayPalError as exc:
        if exc.retryable:
            return "WAITING"
        status, paypal_id, reason = "FAILED", None, exc.name[:120] or "refused"
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.payouts)
            .where(schema.payouts.c.sender_batch_id == batch_id)
            .values(
                status=status,
                paypal_batch_id=paypal_id,
                failure_reason=reason,
                updated_at=int(time.time()),
            )
        )
    audit.record("system", f"payout.{status.lower()}", order["id"], str(row["net_amount"]))
    if status == "FAILED":
        _tell_payout_failed(order, reason)
    return status


def _tell_payout_failed(order: dict, reason: str) -> None:
    if order["simulated"]:
        return
    notify(
        order["seller_user_id"],
        "seller.payout_failed",
        f"We could not pay you for {safe_text(order['title'])}",
        "PayPal did not deliver the payout to your payout email. Check that it is the email of "
        "your PayPal account, change it in your seller console if needed, and Maxx will send the "
        "payout again once it is confirmed.",
        "/sell",
        f"payout-failed:{order['id']}:{reason[:20]}",
    )


def apply_payout_item(batch_id: str, item: dict) -> str:
    """Record what PayPal says happened to one payout item (from a webhook or a poll)."""
    status = item.get("status", "").upper()
    if not status:
        return "ignored"
    p = schema.payouts.c
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.payouts).where(
                (p.payout_item_id == item.get("payout_item_id"))
                | ((p.paypal_batch_id == batch_id) & (p.paypal_batch_id.is_not(None)))
            )
        ).first()
    if row is None:
        return "unknown payout"
    row = dict(row._mapping)
    fields: dict = {
        "payout_item_id": item.get("payout_item_id") or row["payout_item_id"],
        "item_status": status[:20],
        "item_checked_at": int(time.time()),
    }
    failed = status in PAYOUT_FAILED
    if failed and row["status"] != "FAILED":
        fields.update(status="FAILED", failure_reason=(item.get("error") or status)[:120])
    with storage.get_store().engine.begin() as db:
        db.execute(update(schema.payouts).where(p.id == row["id"]).values(**fields))
    order = store.get_order(row["order_id"]) if row["order_id"] else None
    if failed and row["status"] != "FAILED" and order:
        audit.record("paypal", "payout.failed", order["id"], status)
        _tell_payout_failed(order, status)
    if status in PAYOUT_DONE and row["item_status"] not in PAYOUT_DONE and order:
        if not order["simulated"]:
            notify(
                order["seller_user_id"],
                "seller.payout_sent",
                f"Paid: ${row['net_amount']} for {safe_text(order['title'])}",
                "PayPal confirms the payout reached your PayPal account.",
                "/sell",
                f"payout-done:{row['id']}",
            )
    return f"payout item {status.lower()}"


async def refresh_payouts(limit: int = 50) -> int:
    """Ask PayPal what happened to recent payout items that have not settled yet."""
    pp = get_paypal()
    if pp is None:
        return 0
    p = schema.payouts.c
    with storage.get_store().engine.connect() as db:
        rows = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.payouts)
                .where(
                    p.status == "SENT",
                    p.paypal_batch_id.is_not(None),
                    ~p.item_status.in_(sorted(PAYOUT_DONE | PAYOUT_FAILED)),
                )
                .order_by(p.updated_at)
                .limit(limit)
            )
        ]
    checked = 0
    for row in rows:
        try:
            items = await pp.get_payout_batch(row["paypal_batch_id"])
        except PayPalError:
            continue
        for item in items:
            apply_payout_item(row["paypal_batch_id"], item)
        checked += 1
    return checked


def retry_failed_payouts(seller_code: str) -> int:
    """After a seller confirms a new payout email, failed payouts are queued again to it."""
    seller = sellers.by_code(seller_code)
    if not seller or not seller["payout_verified"]:
        return 0
    p = schema.payouts.c
    with storage.get_store().engine.begin() as db:
        rows = db.execute(
            select(p.id, p.order_id, p.attempt).where(
                p.seller_id == seller_code, p.status == "FAILED", p.order_id.is_not(None)
            )
        ).all()
        for row in rows:
            attempt = int(row.attempt) + 1
            db.execute(
                update(schema.payouts)
                .where(p.id == row.id)
                .values(
                    status="PENDING",
                    attempt=attempt,
                    sender_batch_id=f"maxx-order-{row.order_id}-r{attempt}",
                    receiver=seller["payout_email"],
                    paypal_batch_id=None,
                    payout_item_id=None,
                    item_status="",
                    failure_reason="",
                    updated_at=int(time.time()),
                )
            )
    if rows:
        audit.record(f"seller:{seller_code}", "payout.retry", seller_code, f"{len(rows)} payouts")
    return len(rows)


# ---- refunds -----------------------------------------------------------------------------------


async def refund_order(order: dict, reason: str, actor: str, final_status: str) -> bool:
    """Return the buyer's money in full, to their PayPal. Idempotent; False if PayPal is down."""
    payment = ledger.get(order["payment_id"])
    pp = get_paypal()
    if pp is None or payment is None:
        return False
    if payment["status"] == "REFUNDED":
        store.update_order(order["id"], None, status=final_status, closed_at=int(time.time()))
        return True
    if payment["status"] != "CAPTURED" or not payment["capture_id"]:
        return False
    try:
        await pp.refund_capture(
            payment["capture_id"],
            Decimal(payment["captured_amount"]),
            request_id=f"refund-{order['id']}",
            note=f"Maxx refund: {reason}"[:120],
        )
    except PayPalError as exc:
        audit.record(actor, "refund.failed", order["id"], exc.name[:80])
        return False
    ledger.update_payment(payment["id"], status="REFUNDED", error=reason[:60])
    store.update_order(
        order["id"],
        None,
        status=final_status,
        closed_at=int(time.time()),
        address_blob=None,
    )
    payout = _payout_for_order(order["id"])
    if payout and payout["status"] in {"SENT"} and not order["simulated"]:
        # The seller already got paid for this order, so they owe it back.
        store.add_adjustment(
            order["seller_code"], order["id"], Decimal(payout["net_amount"]), reason
        )
    audit.record(actor, "refund.sent", order["id"], f"{reason} {payment['captured_amount']}")
    title = safe_text(order["title"])
    notify(
        order["buyer_id"],
        "order.refunded",
        f"Refunded: ${payment['captured_amount']} for {title}",
        "Your full payment is on its way back to your PayPal account. PayPal usually shows it "
        "within a few days.",
        "/orders",
        f"refunded:{order['id']}",
    )
    if not order["simulated"] and order["status"] in {"AWAITING_ADDRESS", "AWAITING_SHIPMENT"}:
        notify(
            order["seller_user_id"],
            "seller.order_cancelled",
            f"Do not ship: {title} was cancelled",
            "The buyer was refunded, so this order is closed. If you already shipped it, "
            "contact Maxx support.",
            "/sell",
            f"cancelled:{order['id']}",
        )
    return True


async def cancel_by_buyer(buyer_id: str, order_id: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != buyer_id:
        raise LookupError("Order not found.")
    if order["status"] not in {"AWAITING_ADDRESS", "AWAITING_SHIPMENT"}:
        raise Refused("It has shipped, so open a problem instead of cancelling.")
    if not await refund_order(order, "cancelled by buyer", f"user:{buyer_id[:8]}", "CANCELLED"):
        raise Refused("PayPal could not refund right now. Nothing changed; try again shortly.")
    return store.get_order(order_id)


async def confirm_delivery(buyer_id: str, order_id: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != buyer_id:
        raise LookupError("Order not found.")
    if order["status"] != "SHIPPED":
        raise Refused("Only a shipped order can be marked as delivered.")
    store.update_order(order_id, {"SHIPPED"}, status="DELIVERED", delivered_at=int(time.time()))
    audit.record(f"user:{buyer_id[:8]}", "order.delivered", order_id)
    await release_payout(order_id)
    return store.get_order(order_id)


# ---- cases -------------------------------------------------------------------------------------


def open_case(buyer_id: str, order_id: str, kind: str, message: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != buyer_id:
        raise LookupError("Order not found.")
    if kind not in CASE_KINDS:
        raise Refused("Choose what went wrong.")
    if order["status"] not in {"SHIPPED", "DELIVERED"}:
        raise Refused("You can report a problem once the seller has shipped the order.")
    if time.time() > order["created_at"] + 60 * DAY:
        raise Refused("This order is too old to open a problem. Contact support.")
    if store.open_case_for(order_id):
        raise Refused("There is already an open problem for this order.")
    case = store.create_case(order_id, buyer_id, kind, message, settings.case_response_hours)
    audit.record(f"user:{buyer_id[:8]}", "case.opened", case["id"], kind)
    if not order["simulated"]:
        notify(
            order["seller_user_id"],
            "seller.case_opened",
            f"Problem reported: {safe_text(order['title'])}",
            f"The buyer reported a problem. Reply by {_date(case['respond_by'])}, or the buyer "
            "is refunded in full and you receive a strike. The payout for this order is paused.",
            "/sell",
            f"case-open:{case['id']}",
        )
    return case


def _case_parties(case_id: str):
    case = store.get_case(case_id)
    if not case:
        raise LookupError("Case not found.")
    return case, store.get_order(case["order_id"])


def post_message(user_id: str, case_id: str, body: str) -> None:
    case, order = _case_parties(case_id)
    if case["status"] != "OPEN":
        raise Refused("This problem is closed.")
    if user_id == order["buyer_id"]:
        actor = "buyer"
    elif user_id == order["seller_user_id"]:
        actor = "seller"
    else:
        raise LookupError("Case not found.")
    store.add_event(case_id, actor, body)
    title = safe_text(order["title"])
    if actor == "seller":
        notify(
            order["buyer_id"],
            "case.reply",
            f"The seller replied about {title}",
            "Read the reply on your orders page. You can answer there, or withdraw the problem "
            "if it is sorted.",
            "/orders",
        )
    elif not order["simulated"]:
        notify(
            order["seller_user_id"],
            "seller.case_reply",
            f"The buyer wrote about {title}",
            "Read the message in the Problems tab of your seller console.",
            "/sell",
        )


async def resolve_case(case_id: str, refund: bool, actor: str, note: str) -> dict:
    case, order = _case_parties(case_id)
    if case["status"] != "OPEN":
        raise Refused("This problem is already closed.")
    if refund:
        if not await refund_order(order, f"case: {note}"[:60], actor, "REFUNDED"):
            raise Refused("PayPal could not refund right now. The case stays open; try again.")
        store.close_case(case_id, "RESOLVED_REFUNDED", note)
    else:
        store.close_case(case_id, "RESOLVED_DECLINED", note)
    who = "maxx" if actor.startswith("admin") else actor.split(":")[0]
    store.add_event(case_id, who if who in {"buyer", "seller", "maxx"} else "seller", note)
    audit.record(actor, "case.resolved", case_id, "refund" if refund else "declined")
    outcome = "with a full refund" if refund else "without a refund"
    notify(
        order["buyer_id"],
        "case.resolved",
        f"Your problem report for {safe_text(order['title'])} is closed",
        f"It was resolved {outcome}. The details are on your orders page.",
        "/orders",
        f"case-resolved-buyer:{case_id}",
    )
    if not order["simulated"]:
        notify(
            order["seller_user_id"],
            "seller.status" if actor.startswith("admin") else "seller.case_reply",
            f"Problem closed {outcome}: {safe_text(order['title'])}",
            "See the Problems tab of your seller console.",
            "/sell",
            f"case-resolved-seller:{case_id}",
        )
    if not refund:
        await release_payout(order["id"])
    return store.get_case(case_id)


async def withdraw_case(buyer_id: str, case_id: str) -> dict:
    case, order = _case_parties(case_id)
    if order["buyer_id"] != buyer_id:
        raise LookupError("Case not found.")
    if not store.close_case(case_id, "WITHDRAWN", "Withdrawn by the buyer."):
        raise Refused("This problem is already closed.")
    audit.record(f"user:{buyer_id[:8]}", "case.withdrawn", case_id)
    await release_payout(order["id"])
    return store.get_case(case_id)


# ---- the simulated sellers' automatic stand-in -------------------------------------------------


def demo_tracking_number() -> str:
    """A well-formed UPS number (valid check digit) for a parcel the simulated seller 'ships'."""
    body = "MAXX01" + "02" + f"{secrets.randbelow(10**7):07d}"
    total = 0
    for index, char in enumerate(body):
        value = int(char) if char.isdigit() else (ord(char) - 3) % 10
        total += value * (2 if index % 2 == 1 else 1)
    check = (10 - total % 10) % 10
    return f"1Z{body}{check}"


async def act_for_simulated_sellers() -> int:
    """Ship and answer for the simulated sellers, as a prompt real seller would."""
    acted = 0
    now = time.time()
    for order in store.orders_in(["AWAITING_SHIPMENT"]):
        if (
            not order["simulated"]
            or now < order["updated_at"] + settings.simulated_seller_ship_seconds
        ):
            continue
        try:
            await ship(SIMULATED_USER, order["id"], "ups", demo_tracking_number())
            acted += 1
        except Refused:
            continue
    for case in store.all_open_cases():
        order = store.get_order(case["order_id"])
        if not order or not order["simulated"]:
            continue
        store.add_event(
            case["id"],
            "seller",
            "Automatic reply from the simulated seller: sorry about this. We refund you in full.",
        )
        try:
            await resolve_case(
                case["id"], True, "simulated-seller", "The simulated seller refunded in full."
            )
            acted += 1
        except Refused:
            continue
    return acted


# ---- the sweep (runs from the worker) ----------------------------------------------------------


def _strike(seller_code: str, reason: str) -> None:
    seller = sellers.by_code(seller_code)
    if not seller:
        return
    strikes = int(seller["strikes"]) + 1
    fields: dict = {"strikes": strikes}
    if strikes >= 3 and seller["status"] == "ACTIVE":
        fields.update(
            status="SUSPENDED", review_note="Suspended after repeated missed commitments."
        )
        audit.record("system", "seller.suspended", seller_code, f"{strikes} strikes")
    sellers.update_seller(seller["id"], **fields)
    audit.record("system", "seller.strike", seller_code, reason)
    notify(
        seller["user_id"],
        "seller.strike",
        f"Strike {strikes} of 3: {reason}",
        "A missed shipping deadline or an unanswered problem report counts against your account. "
        + (
            "Your account is now suspended."
            if strikes >= 3
            else "Three strikes suspend the account."
        ),
        "/sell",
    )


def _remind(now: int) -> int:
    sent = 0
    for order in store.orders_in(["AWAITING_ADDRESS"]):
        if 0 < order["ship_by"] - now <= DAY:
            sent += notify(
                order["buyer_id"],
                "order.address_reminder",
                f"One day left to add an address for {safe_text(order['title'])}",
                "Without a delivery address the order is cancelled and refunded.",
                "/orders",
                f"address-reminder:{order['id']}",
            )
    for order in store.orders_in(["AWAITING_SHIPMENT"]):
        if not order["simulated"] and 0 < order["ship_by"] - now <= DAY:
            sent += notify(
                order["seller_user_id"],
                "seller.ship_reminder",
                f"Ship {safe_text(order['title'])} by {_date(order['ship_by'])}",
                "After the deadline and a short grace period the buyer is refunded and you "
                "receive a strike.",
                "/sell",
                f"ship-reminder:{order['id']}",
            )
    for case in store.all_open_cases():
        order = store.get_order(case["order_id"])
        if order and not order["simulated"] and 0 < case["respond_by"] - now <= 6 * 3600:
            if not any(e["actor"] == "seller" for e in store.events_for(case["id"])):
                sent += notify(
                    order["seller_user_id"],
                    "seller.case_reminder",
                    f"Reply about {safe_text(order['title'])} within 6 hours",
                    "If you do not reply, the buyer is refunded in full and you receive a strike.",
                    "/sell",
                    f"case-reminder:{case['id']}",
                )
    return sent


async def sweep() -> dict:
    """Enforce the deadlines. Safe to run often and after a crash."""
    done = {
        "refunded": 0,
        "paid": 0,
        "delivered": 0,
        "purged": 0,
        "case_refunds": 0,
        "tracked": 0,
        "reminded": 0,
        "simulated": 0,
        "payout_checks": 0,
    }
    if get_paypal() is None:
        return done
    now = int(time.time())
    for order in store.orders_in(["AWAITING_ADDRESS"]):
        if now > order["ship_by"] and await refund_order(
            order, "no delivery address", "system", "CANCELLED"
        ):
            done["refunded"] += 1
    for order in store.orders_in(["AWAITING_SHIPMENT"]):
        if now > order["ship_by"] + settings.ship_grace_days * DAY:
            if await refund_order(order, "not shipped in time", "system", "CANCELLED"):
                if not order["simulated"]:
                    _strike(order["seller_code"], f"order {order['id'][:8]} not shipped")
                done["refunded"] += 1
    for case in store.all_open_cases():
        if now > case["respond_by"] and not any(
            e["actor"] == "seller" for e in store.events_for(case["id"])
        ):
            order = store.get_order(case["order_id"])
            if order and await refund_order(order, "seller did not respond", "system", "REFUNDED"):
                store.close_case(case["id"], "RESOLVED_REFUNDED", "The seller did not respond.")
                if not order["simulated"]:
                    _strike(order["seller_code"], f"case {case['id'][:8]} unanswered")
                done["case_refunds"] += 1
    poll = min(settings.tracking_poll_minutes * 60, settings.tracking_sim_step_seconds)
    for order in store.orders_in(["SHIPPED", "DELIVERED"]):
        stale = (order["tracking_checked_at"] or 0) < now - (
            poll
            if order["tracker_id"] and order["tracker_id"].startswith("SIM-")
            else settings.tracking_poll_minutes * 60
        )
        if order["tracker_id"] and stale and order["tracking_status"] != "delivered":
            if await refresh_tracking(order):
                done["tracked"] += 1
            order = store.get_order(order["id"])
        if (
            order["status"] == "SHIPPED"
            and order["tracker_id"]
            and not order["first_scan_at"]
            and not order["review_flag"]  # a person may already have cleared it
            and now > (order["shipped_at"] or now) + settings.tracking_no_scan_days * DAY
        ):
            flag = "The carrier has not scanned the parcel since it was marked shipped."
            store.update_order(order["id"], None, review_flag=flag)
            audit.record("system", "order.flagged", order["id"], "no carrier scan")
            notify(
                order["buyer_id"],
                "order.tracking_issue",
                f"{safe_text(order['title'])} has not moved yet",
                "The carrier has not received the parcel. If it does not arrive, report a "
                "problem on your orders page for a full refund.",
                "/orders",
                f"no-scan-buyer:{order['id']}",
            )
            if not order["simulated"]:
                notify(
                    order["seller_user_id"],
                    "seller.tracking_issue",
                    f"No carrier scan for {safe_text(order['title'])}",
                    "The parcel has not been scanned by the carrier. Hand it over, or contact "
                    "the carrier. The payout is on hold until it moves.",
                    "/sell",
                    f"no-scan-seller:{order['id']}",
                )
        payout = _payout_for_order(order["id"])
        if payout is None or payout["status"] == "PENDING":
            if await release_payout(order["id"]) in {"SENT", "OFFSET"}:
                done["paid"] += 1
        if (
            order["status"] == "SHIPPED"
            and order["shipped_at"]
            and now > order["shipped_at"] + settings.delivery_auto_confirm_days * DAY
            and not store.open_case_for(order["id"])
            and not flagged(order)
            and store.update_order(order["id"], {"SHIPPED"}, status="DELIVERED", delivered_at=now)
        ):
            done["delivered"] += 1
            await release_payout(order["id"])
    done["payout_checks"] = await refresh_payouts()
    if settings.simulated_sellers:
        done["simulated"] = await act_for_simulated_sellers()
    done["reminded"] = _remind(now)
    cutoff = now - settings.address_retention_days * DAY
    for order in store.orders_in(["DELIVERED", "CANCELLED", "REFUNDED"]):
        closed = order["closed_at"] or order["delivered_at"] or order["updated_at"]
        if order["address_blob"] and closed < cutoff:
            store.update_order(order["id"], None, address_blob=None)
            done["purged"] += 1
    return done
