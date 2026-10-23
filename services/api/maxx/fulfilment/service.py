"""Marketplace rules between a captured payment and a happy buyer.

Maxx does not ship, inspect or insure goods; the seller does. Maxx coordinates, and protects the
buyer's money until the seller has shipped:

  captured -> order awaits a delivery address -> awaits shipment -> shipped (seller is paid)
  no address in time, or not shipped in time, or buyer cancels before shipping -> full refund
  problem after shipping -> a case; the seller replies; Maxx rules if they disagree

Every state change is guarded (only from the expected state) and written to the audit log.
"""

from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from maxx import audit, schema, storage
from maxx.config import settings
from maxx.fulfilment import store
from maxx.money import ledger
from maxx.money.paypal import CENTS, PayPalError, get_paypal
from maxx.negotiate.contracts import Bloc
from maxx.sellers import store as sellers

log = logging.getLogger(__name__)
DAY = 86400
CASE_KINDS = {"not_received", "not_as_described", "return_request", "other"}


class Refused(ValueError):
    """A rule said no. The message is safe to show the person."""


def _fee(gross: Decimal) -> Decimal:
    return (gross * Decimal(settings.platform_fee_percent) / 100).quantize(CENTS)


# ---- creation ----------------------------------------------------------------------------------


def create_orders(bloc: Bloc) -> int:
    """After a Bloc settles, give every real buyer who won from a real seller an order."""
    made = 0
    members = {m.id: m for m in bloc.members}
    real = {s.id: s for s in bloc.sellers if s.account_id}
    for payment in ledger.for_bloc(bloc.id, bloc.generation):
        if payment["kind"] != "hold" or payment["status"] != "CAPTURED":
            continue
        member = members.get(payment["member_id"] or "")
        seller = real.get(member.seller_id or "") if member else None
        if member is None or seller is None or seller.account_id is None:
            continue
        order = store.create_order(
            payment["id"],
            bloc.id,
            bloc.generation,
            payment["user_id"],
            seller.id,
            seller.account_id,
            bloc.title,
            Decimal(payment["captured_amount"]),
            payment["currency"],
            int(time.time()) + settings.address_wait_days * DAY,
        )
        if order:
            made += 1
            audit.record("system", "order.created", order["id"], f"{bloc.id} seller {seller.id}")
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
    seller = sellers.by_code(order["seller_code"])
    fields: dict = {"address_blob": address["ciphertext"], "address_country": address["country"]}
    if seller and seller["ships_to"] and address["country"] not in seller["ships_to"].split(","):
        raise Refused(
            "This seller does not ship to that country. Choose another address or cancel."
        )
    if order["status"] == "AWAITING_ADDRESS":
        days = seller["ship_within_days"] if seller else 3
        fields.update(status="AWAITING_SHIPMENT", ship_by=int(time.time()) + days * DAY)
    store.update_order(order_id, {"AWAITING_ADDRESS", "AWAITING_SHIPMENT"}, **fields)
    audit.record(f"user:{buyer_id[:8]}", "order.address", order_id)
    return store.get_order(order_id)


# ---- seller: ship and get paid -----------------------------------------------------------------


async def ship(seller_user_id: str, order_id: str, carrier: str, tracking: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["seller_user_id"] != seller_user_id:
        raise LookupError("Order not found.")
    if order["status"] == "AWAITING_ADDRESS":
        raise Refused("The buyer has not given a delivery address yet.")
    if order["status"] != "AWAITING_SHIPMENT":
        raise Refused("This order can no longer be marked as shipped.")
    if not store.update_order(
        order_id,
        {"AWAITING_SHIPMENT"},
        status="SHIPPED",
        carrier=carrier,
        tracking=tracking,
        shipped_at=int(time.time()),
    ):
        raise Refused("This order changed. Refresh and try again.")
    audit.record(f"seller:{order['seller_code']}", "order.shipped", order_id, carrier)
    await release_payout(order_id)
    return store.get_order(order_id)


def _payout_for_order(order_id: str) -> dict | None:
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.payouts).where(schema.payouts.c.order_id == order_id)
        ).first()
    return dict(row._mapping) if row else None


async def release_payout(order_id: str) -> str:
    """Pay the seller for a shipped order, once. Returns SENT, FAILED, WAITING or NONE."""
    order = store.get_order(order_id)
    pp = get_paypal()
    if pp is None or not order or order["status"] not in {"SHIPPED", "DELIVERED"}:
        return "NONE"
    existing = _payout_for_order(order_id)
    if existing and existing["status"] in {"SENT", "OFFSET"}:
        return existing["status"]
    if store.open_case_for(order_id):
        return "WAITING"  # a dispute pauses the money
    if audit.payments_frozen():
        return "WAITING"
    seller = sellers.by_code(order["seller_code"])
    if not seller or seller["status"] != "ACTIVE" or not seller["payout_verified"]:
        return "WAITING"
    cooldown = settings.payout_cooldown_hours * 3600
    if seller["payout_verified_at"] and time.time() < seller["payout_verified_at"] + cooldown:
        return "WAITING"  # a newly confirmed address is not paid immediately
    gross = Decimal(order["amount"])
    fee = _fee(gross)
    stamp = int(time.time())
    batch_id = f"maxx-order-{order_id}"
    if existing is None:
        net = gross - fee
        taken = store.take_adjustments(order["seller_code"], net)
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
            "sender_batch_id": batch_id,
            "paypal_batch_id": None,
            "receiver": seller["payout_email"],
            "status": "OFFSET" if net <= 0 else "PENDING",
            "tx_hash": None,
            "simulated": pp.simulated,
            "created_at": stamp,
            "updated_at": stamp,
            "order_id": order_id,
        }
        try:
            with storage.get_store().engine.begin() as db:
                db.execute(schema.payouts.insert().values(**row))
        except IntegrityError:
            existing = _payout_for_order(order_id)
            row = existing
        if row["status"] == "OFFSET":
            audit.record("system", "payout.offset", order_id, f"owed {taken}")
            return "OFFSET"
    else:
        row = existing
    try:
        batch = await pp.create_payout(
            batch_id,
            [
                {
                    "receiver": row["receiver"],
                    "amount": row["net_amount"],
                    "sender_item_id": f"order-{order_id}"[:63],
                    "note": f"Maxx order {order['title'][:60]}",
                }
            ],
        )
        status, paypal_id = "SENT", batch["batch_id"]
    except PayPalError as exc:
        if exc.retryable:
            return "WAITING"
        status, paypal_id = "FAILED", None
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.payouts)
            .where(schema.payouts.c.sender_batch_id == batch_id)
            .values(status=status, paypal_batch_id=paypal_id, updated_at=int(time.time()))
        )
    audit.record("system", f"payout.{status.lower()}", order_id, str(row["net_amount"]))
    return status


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
    if payout and payout["status"] in {"SENT"}:
        # The seller already got paid for this order, so they owe it back.
        store.add_adjustment(
            order["seller_code"], order["id"], Decimal(payout["net_amount"]), reason
        )
    audit.record(actor, "refund.sent", order["id"], f"{reason} {payment['captured_amount']}")
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


def confirm_delivery(buyer_id: str, order_id: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != buyer_id:
        raise LookupError("Order not found.")
    if order["status"] != "SHIPPED":
        raise Refused("Only a shipped order can be marked as delivered.")
    store.update_order(order_id, {"SHIPPED"}, status="DELIVERED", delivered_at=int(time.time()))
    audit.record(f"user:{buyer_id[:8]}", "order.delivered", order_id)
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
    store.add_event(case_id, "maxx" if actor.startswith("admin") else actor.split(":")[0], note)
    audit.record(actor, "case.resolved", case_id, "refund" if refund else "declined")
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


async def sweep() -> dict:
    """Enforce the deadlines. Safe to run often and after a crash."""
    done = {"refunded": 0, "paid": 0, "delivered": 0, "purged": 0, "case_refunds": 0}
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
                _strike(order["seller_code"], f"order {order['id'][:8]} not shipped")
                done["refunded"] += 1
    for case in store.all_open_cases():
        if now > case["respond_by"] and not any(
            e["actor"] == "seller" for e in store.events_for(case["id"])
        ):
            order = store.get_order(case["order_id"])
            if order and await refund_order(order, "seller did not respond", "system", "REFUNDED"):
                store.close_case(case["id"], "RESOLVED_REFUNDED", "The seller did not respond.")
                _strike(order["seller_code"], f"case {case['id'][:8]} unanswered")
                done["case_refunds"] += 1
    for order in store.orders_in(["SHIPPED", "DELIVERED"]):
        if (
            _payout_for_order(order["id"]) is None
            or (_payout_for_order(order["id"]) or {}).get("status") == "PENDING"
        ):
            if await release_payout(order["id"]) in {"SENT", "OFFSET"}:
                done["paid"] += 1
        if (
            order["status"] == "SHIPPED"
            and order["shipped_at"]
            and now > order["shipped_at"] + settings.delivery_auto_confirm_days * DAY
            and not store.open_case_for(order["id"])
            and store.update_order(order["id"], {"SHIPPED"}, status="DELIVERED", delivered_at=now)
        ):
            done["delivered"] += 1
    cutoff = now - settings.address_retention_days * DAY
    for order in store.orders_in(["DELIVERED", "CANCELLED", "REFUNDED"]):
        closed = order["closed_at"] or order["delivered_at"] or order["updated_at"]
        if order["address_blob"] and closed < cutoff:
            store.update_order(order["id"], None, address_blob=None)
            done["purged"] += 1
    return done
