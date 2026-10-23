"""Holds, settlement and payouts.

Money moves only from a cleared Bloc, and never above a member's maximum.

Order of events for a Bloc:
  join   -> order (intent AUTHORIZE) -> buyer approves -> authorize -> member added, hold in ledger
  leave  -> hold voided
  clear  -> winners captured at their final price (final_capture releases the rest), everyone else
            voided, then sellers paid out net of the platform fee
  fail   -> every hold voided
Every PayPal write has a deterministic request id and every step is recorded first, so a crash
anywhere resumes without capturing twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from maxx import audit, schema, storage
from maxx.config import settings
from maxx.money import ledger
from maxx.money.paypal import CENTS, PayPalError, get_paypal
from maxx.negotiate.blocs import add_member, leave_member
from maxx.negotiate.contracts import Bloc
from maxx.negotiate.store import Conflict

log = logging.getLogger(__name__)


def enabled() -> bool:
    return settings.paypal_mode in {"simulator", "sandbox"}


def fee_for(gross: Decimal) -> Decimal:
    return (gross * Decimal(settings.platform_fee_percent) / 100).quantize(CENTS)


def _fail(reason: str) -> ValueError:
    return ValueError(reason)


def _check_limits(user_id: str, amount: Decimal) -> None:
    """Cap how much a single account can have on hold at once (fraud and runaway-spend guard)."""
    open_holds = [
        p
        for p in ledger.for_user(user_id)
        if p["kind"] == "hold" and p["status"] in {"CREATED", "APPROVED", "AUTHORIZED"}
    ]
    if len(open_holds) >= settings.hold_open_max_per_user:
        raise _fail("You have many open holds. Wait for some Blocs to finish first.")
    total = sum((Decimal(p["max_amount"]) for p in open_holds), Decimal(0)) + amount
    if total > Decimal(settings.hold_outstanding_max_per_user):
        raise _fail(
            f"Your open holds would exceed ${settings.hold_outstanding_max_per_user} in total."
        )


async def start_hold(bloc: Bloc, user_id: str, max_price: Decimal, test_case: str = "") -> dict:
    """Create the PayPal order for a join. The buyer then approves it on PayPal."""
    pp = get_paypal()
    if pp is None:
        raise _fail("Payments are turned off.")
    if audit.payments_frozen():
        raise _fail("New holds are paused for maintenance. Nothing was charged. Try again later.")
    if max_price > Decimal(settings.hold_max_amount):
        raise _fail(f"A single hold is limited to ${settings.hold_max_amount}.")
    if bloc.origin == "demo_tour" and not user_id.startswith("demo-buyer-"):
        raise _fail("This Bloc belongs to a seller tour demo and is not open to buyers.")
    _check_limits(user_id, max_price)
    from maxx.sellers import store as seller_store

    own = seller_store.by_user(user_id)
    if own and any(
        o["product_key"] == bloc.product_key for o in seller_store.offers_for(own["id"])
    ):
        raise _fail("Sellers cannot buy a product they have an offer on.")
    # Validate with the same rules as joining, on a throwaway copy, before touching PayPal.
    add_member(bloc.model_copy(deep=True), user_id, str(max_price))
    if any(m.user_id == user_id and m.status == "HELD" for m in bloc.members):
        raise _fail("You already joined this Bloc. Leave it to change your maximum.")
    stale = ledger.active_hold(bloc.id, bloc.generation, user_id)
    if stale and stale["status"] in {"CREATED", "APPROVED"}:
        if Decimal(stale["max_amount"]) == max_price and stale["meta"] == test_case:
            return stale
        ledger.update_payment(stale["id"], status="FAILED", error="replaced")
    elif stale:
        raise _fail("You already have a hold on this Bloc.")
    order = await pp.create_order(
        max_price,
        reference=f"{bloc.id}",
        request_id=f"order-{uuid.uuid4()}",
        description=f"Hold for {bloc.title}"[:127],
        mock=test_case or None,
    )
    return ledger.new_payment(
        "hold",
        order["id"],
        max_price,
        pp.simulated,
        user_id=user_id,
        bloc_id=bloc.id,
        generation=bloc.generation,
        meta=test_case,
    )


async def authorize_hold(store, user_id: str, order_id: str) -> tuple[Bloc, dict]:
    pp = get_paypal()
    if pp is None:
        raise _fail("Payments are turned off.")
    payment = ledger.by_order(order_id)
    if not payment or payment["user_id"] != user_id or payment["kind"] != "hold":
        raise LookupError("Order not found.")
    if payment["status"] == "AUTHORIZED":
        return store.get(payment["bloc_id"]), payment
    if payment["status"] not in {"CREATED", "APPROVED"}:
        raise _fail("This order can no longer be used.")
    bloc = store.get(payment["bloc_id"])
    if bloc.generation != payment["generation"] or bloc.status != "OPEN":
        ledger.update_payment(payment["id"], status="FAILED", error="bloc_closed")
        raise _fail("This Bloc is no longer open for joining.")
    order = await pp.get_order(order_id)
    if order["status"] != "APPROVED":
        raise _fail("Approve the hold in PayPal first.")
    try:
        auth = await pp.authorize_order(order_id, request_id=f"auth-{payment['id']}")
    except PayPalError as exc:
        ledger.update_payment(payment["id"], status="FAILED", error=exc.name[:60] or "declined")
        raise _fail("PayPal could not place the hold. Try another payment method.") from exc
    ledger.update_payment(
        payment["id"], status="AUTHORIZED", authorization_id=auth["authorization_id"]
    )
    for _ in range(5):
        try:
            add_member(bloc, user_id, str(payment["max_amount"]))
            store.save(bloc)
            break
        except Conflict:
            bloc = store.get(payment["bloc_id"])
        except ValueError as exc:
            await _void(pp, payment["id"], auth["authorization_id"], "join_failed")
            raise _fail(str(exc)) from exc
    else:
        await _void(pp, payment["id"], auth["authorization_id"], "join_conflict")
        raise _fail("The Bloc changed while you joined. Your hold was released; try again.")
    member = next(m for m in bloc.members if m.user_id == user_id and m.status == "HELD")
    ledger.update_payment(payment["id"], member_id=member.id)
    audit.record(f"user:{user_id[:8]}", "hold.placed", payment["id"], f"{payment['max_amount']}")
    return bloc, ledger.get(payment["id"])


async def _void(pp, payment_id: str, authorization_id: str, reason: str) -> bool:
    try:
        await pp.void_authorization(authorization_id, request_id=f"void-{payment_id}")
    except PayPalError:
        ledger.update_payment(payment_id, status="VOID_PENDING", error=reason)
        return False
    ledger.update_payment(payment_id, status="VOIDED", error=reason)
    return True


async def leave(store, bloc: Bloc, user_id: str) -> None:
    """Leave a Bloc and release the hold. The member is marked LEFT first, so a PayPal outage can
    only delay the release, never leave a buyer committed."""
    held = next((m for m in bloc.members if m.user_id == user_id and m.status == "HELD"), None)
    leave_member(bloc, user_id)
    store.save(bloc)
    pp = get_paypal()
    if pp is None or held is None:
        return
    for payment in ledger.for_bloc(bloc.id, bloc.generation):
        if payment["member_id"] == held.id and payment["status"] == "AUTHORIZED":
            await _void(pp, payment["id"], payment["authorization_id"], "left")


async def cancel_unfinished(user_id: str, order_id: str) -> None:
    payment = ledger.by_order(order_id)
    if payment and payment["user_id"] == user_id and payment["status"] in {"CREATED", "APPROVED"}:
        ledger.update_payment(payment["id"], status="FAILED", error="cancelled")


# ---- settlement -------------------------------------------------------------------------------


def _claim(bloc_id: str, generation: int) -> bool:
    """Take the settlement for this Bloc, unless it is done or another worker is on it."""
    table = schema.settlements
    stamp = int(time.time())
    engine = storage.get_store().engine
    try:
        with engine.begin() as db:
            db.execute(
                table.insert().values(
                    bloc_id=bloc_id, generation=generation, status="RUNNING", started_at=stamp
                )
            )
        return True
    except IntegrityError:
        pass
    with engine.begin() as db:
        row = db.execute(
            select(table.c.status, table.c.started_at).where(
                table.c.bloc_id == bloc_id, table.c.generation == generation
            )
        ).first()
        if row.status == "DONE" or (row.status == "RUNNING" and stamp - row.started_at < 300):
            return False
        taken = db.execute(
            update(table)
            .where(
                table.c.bloc_id == bloc_id,
                table.c.generation == generation,
                table.c.status == row.status,
                table.c.started_at == row.started_at,
            )
            .values(status="RUNNING", started_at=stamp)
        )
        return taken.rowcount == 1


def _finish(bloc_id: str, generation: int, status: str, summary: dict) -> None:
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.settlements)
            .where(
                schema.settlements.c.bloc_id == bloc_id,
                schema.settlements.c.generation == generation,
            )
            .values(status=status, finished_at=int(time.time()), summary=json.dumps(summary))
        )


def settlement_status(bloc_id: str, generation: int) -> str | None:
    with storage.get_store().engine.connect() as db:
        return db.execute(
            select(schema.settlements.c.status).where(
                schema.settlements.c.bloc_id == bloc_id,
                schema.settlements.c.generation == generation,
            )
        ).scalar()


def pending_bloc_ids(store) -> list[str]:
    """Finished Blocs that may still owe PayPal work, found without loading any Bloc document."""
    with storage.get_store().engine.connect() as db:
        holds = db.execute(
            select(schema.payments.c.bloc_id, schema.payments.c.generation)
            .where(
                schema.payments.c.kind == "hold",
                schema.payments.c.status.in_(["AUTHORIZED", "VOID_PENDING"]),
            )
            .distinct()
        ).all()
        partial = db.execute(
            select(schema.settlements.c.bloc_id, schema.settlements.c.generation).where(
                schema.settlements.c.status == "PARTIAL"
            )
        ).all()
    found = []
    for bloc_id, generation in {*map(tuple, holds), *map(tuple, partial)}:
        meta = store.meta(bloc_id)
        if meta and meta["generation"] == generation and meta["status"] in {"SETTLED", "FAILED"}:
            found.append(bloc_id)
    return found


def needs_settlement(bloc: Bloc) -> bool:
    if not enabled() or bloc.status not in {"SETTLED", "FAILED"}:
        return False
    if settlement_status(bloc.id, bloc.generation) in {"DONE", "RUNNING"}:
        return False
    return (
        any(
            p["status"] in {"AUTHORIZED", "VOID_PENDING"}
            for p in ledger.for_bloc(bloc.id, bloc.generation)
        )
        or settlement_status(bloc.id, bloc.generation) == "PARTIAL"
    )


async def settle_bloc(store, bloc_id: str) -> dict:
    """Capture winners, release everyone else, pay sellers. Safe to run again after a crash."""
    pp = get_paypal()
    bloc = store.get(bloc_id)
    if pp is None or bloc.status not in {"SETTLED", "FAILED"}:
        return {}
    if not _claim(bloc.id, bloc.generation):
        return {}
    outcome = {"captured": 0, "voided": 0, "failed": 0, "retry": 0}
    frozen = audit.payments_frozen()
    members = {m.id: m for m in bloc.members}
    gate = asyncio.Semaphore(settings.settlement_concurrency)

    async def one(payment: dict):
        async with gate:
            member = members.get(payment["member_id"] or "")
            winner = (
                bloc.status == "SETTLED"
                and member is not None
                and member.status == "WIN"
                and member.final_price is not None
            )
            try:
                if winner and frozen:
                    outcome["retry"] += 1  # paused: the hold stays safely in place
                    return
                if payment["status"] == "VOID_PENDING" or not winner:
                    ok = await _void(
                        pp, payment["id"], payment["authorization_id"], "not_allocated"
                    )
                    outcome["voided" if ok else "retry"] += 1
                    return
                amount = min(
                    Decimal(member.final_price), Decimal(payment["max_amount"]), member.max_price
                )
                capture = await pp.capture_authorization(
                    payment["authorization_id"],
                    amount,
                    request_id=f"cap-{payment['id']}",
                    mock=payment["meta"] or None,
                )
                ledger.update_payment(
                    payment["id"],
                    status="CAPTURED",
                    capture_id=capture["capture_id"],
                    captured_amount=amount,
                )
                outcome["captured"] += 1
                audit.record("system", "payment.captured", payment["id"], str(amount))
            except PayPalError as exc:
                if exc.retryable:
                    outcome["retry"] += 1
                else:
                    ledger.update_payment(
                        payment["id"], status="CAPTURE_FAILED", error=exc.name[:60] or "failed"
                    )
                    outcome["failed"] += 1

    work = [
        p
        for p in ledger.for_bloc(bloc.id, bloc.generation)
        if p["kind"] == "hold" and p["status"] in {"AUTHORIZED", "VOID_PENDING"}
    ]
    await asyncio.gather(*(one(p) for p in work))
    if bloc.status == "SETTLED":
        from maxx.fulfilment import service as fulfilment

        # Every winner gets an order; each seller (real or simulated) is paid per order, when the
        # carrier confirms it shipped (see fulfilment). Nothing is paid out at settlement.
        fulfilment.create_orders(bloc)
    _tell_outcome(bloc)
    done = outcome["retry"] == 0
    _finish(bloc.id, bloc.generation, "DONE" if done else "PARTIAL", outcome)
    return outcome


def _tell_outcome(bloc: Bloc) -> None:
    """Tell buyers whose hold was released, and real sellers what their offer won."""
    from maxx.notify.service import notify, safe_text

    members = {m.id: m for m in bloc.members}
    title = safe_text(bloc.title)
    for payment in ledger.for_bloc(bloc.id, bloc.generation):
        member = members.get(payment["member_id"] or "")
        if (
            payment["kind"] != "hold"
            or payment["status"] != "VOIDED"
            or payment["error"] != "not_allocated"  # released at settlement, not by leaving
            or member is None
        ):
            continue
        reason = (
            "No seller met the group's prices, so there was no deal."
            if bloc.status == "FAILED"
            else "The deal could not serve every buyer within their maximum, and yours was not "
            "reached."
        )
        notify(
            payment["user_id"],
            "bloc.released",
            f"Your hold for {title} was released",
            f"{reason} Nothing was charged; PayPal releases the hold.",
            f"/blocs/{bloc.id}/room",
            f"released:{payment['id']}",
        )
    if bloc.status != "SETTLED" or bloc.outcome is None:
        return
    for seller in bloc.sellers:
        if not seller.account_id:
            continue
        units = [a for a in bloc.outcome.allocations if a.seller_id == seller.id]
        notify(
            seller.account_id,
            "seller.bloc_result",
            f"Your offer won {len(units)} unit{'s' if len(units) != 1 else ''} of {title}"
            if units
            else f"Your offer did not win in {title}",
            "Orders from paying buyers appear in your seller console; ship each one when the "
            "buyer gives an address."
            if units
            else "Other offers were cheaper this time. Your standing offer stays on file.",
            "/sell",
            f"bloc-result:{bloc.id}:{bloc.generation}:{seller.id}",
        )


async def release_orphans(store) -> int:
    """Void holds that belong to a Bloc generation that no longer exists (for example after a demo
    reset), so nobody's money stays held for a negotiation that can never settle."""
    pp = get_paypal()
    if pp is None:
        return 0
    current = store.generations()
    released = 0
    with storage.get_store().engine.connect() as db:
        rows = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.payments).where(
                    schema.payments.c.kind == "hold",
                    schema.payments.c.status.in_(["AUTHORIZED", "VOID_PENDING"]),
                )
            )
        ]
    for payment in rows:
        if current.get(payment["bloc_id"]) != payment["generation"]:
            released += await _void(pp, payment["id"], payment["authorization_id"], "bloc_replaced")
    return released


def payout_rows(bloc_id: str, generation: int | None = None) -> list[dict]:
    query = select(schema.payouts).where(schema.payouts.c.bloc_id == bloc_id)
    if generation is not None:
        query = query.where(schema.payouts.c.generation == generation)
    with storage.get_store().engine.connect() as db:
        return [dict(r._mapping) for r in db.execute(query.order_by(schema.payouts.c.seller_id))]


def reconcile(bloc_id: str, generation: int | None = None) -> dict:
    """Tie out the books: money still captured is either paid out (fee plus seller share), or
    being held until the seller ships. Refunded money is accounted for separately."""
    from maxx.fulfilment import store as fulfilment

    payments = [p for p in ledger.for_bloc(bloc_id, generation) if p["kind"] == "hold"]
    payouts = payout_rows(bloc_id, generation)
    orders = [
        o
        for o in fulfilment.orders_where(bloc_id=bloc_id)
        if generation is None or o["generation"] == generation
    ]
    refunded_orders = {
        o["id"] for o in orders if (ledger.get(o["payment_id"]) or {}).get("status") == "REFUNDED"
    }
    ordered_payments = {o["payment_id"]: o["id"] for o in orders}
    paid_orders = {p["order_id"] for p in payouts if p.get("order_id")}

    def total(rows, key):
        return sum((Decimal(r[key]) for r in rows), Decimal("0.00")).quantize(CENTS)

    held = [p for p in payments if p["status"] == "AUTHORIZED"]
    captured = [p for p in payments if p["status"] == "CAPTURED"]
    refunded = [p for p in payments if p["status"] == "REFUNDED"]
    voided = [p for p in payments if p["status"] == "VOIDED"]
    # Payouts for refunded orders are the seller's debt, not part of the live books.
    live = [p for p in payouts if p.get("order_id") not in refunded_orders]
    sent = [p for p in live if p["status"] in {"SENT", "OFFSET"}]
    waiting = [
        p
        for p in captured
        if p["id"] in ordered_payments and ordered_payments[p["id"]] not in paid_orders
    ]
    captured_total = total(captured, "captured_amount")
    grouped: dict[str, dict] = {}
    for row in live:
        seller = grouped.setdefault(
            row["seller_id"],
            {
                "seller": row["seller_id"],
                "method": row["method"],
                "units": 0,
                "gross": Decimal(0),
                "fee": Decimal(0),
                "net": Decimal(0),
                "statuses": set(),
                "simulated": bool(row["simulated"]),
            },
        )
        seller["units"] += row["units"]
        seller["gross"] += Decimal(row["gross_amount"])
        seller["fee"] += Decimal(row["fee_amount"])
        seller["net"] += Decimal(row["net_amount"])
        seller["statuses"].add(row["status"])
    return {
        "currency": settings.paypal_currency,
        "holds": len(payments),
        "held_total": str(total(held, "max_amount")),
        "captured_count": len(captured),
        "captured_total": str(captured_total),
        "voided_count": len(voided),
        "voided_total": str(total(voided, "max_amount")),
        "refunded_count": len(refunded),
        "refunded_total": str(total(refunded, "captured_amount")),
        "failed_count": sum(p["status"] in {"CAPTURE_FAILED", "FAILED"} for p in payments),
        "platform_fee": str(total(live, "fee_amount")),
        "seller_payouts": str(total(sent, "net_amount")),
        "held_for_shipping": str(total(waiting, "captured_amount")),
        "payouts": [
            {
                "seller": g["seller"],
                "method": g["method"],
                "units": g["units"],
                "gross": str(g["gross"].quantize(CENTS)),
                "fee": str(g["fee"].quantize(CENTS)),
                "net": str(g["net"].quantize(CENTS)),
                "status": next(iter(g["statuses"])) if len(g["statuses"]) == 1 else "MIXED",
                "simulated": g["simulated"],
            }
            for g in grouped.values()
        ],
        "reconciled": bool(captured)
        and captured_total == total(live, "gross_amount") + total(waiting, "captured_amount")
        and all(p["status"] in {"SENT", "OFFSET"} for p in live),
    }


async def verify_remote(limit: int = 200) -> dict:
    """Compare what the ledger believes with what PayPal says, for recent payments.
    Returns the mismatches. Safe to run any time; it only reads."""
    pp = get_paypal()
    if pp is None:
        return {"checked": 0, "mismatches": []}
    expected = {
        "AUTHORIZED": {"CREATED", "PENDING"},
        "VOIDED": {"VOIDED"},
        "CAPTURED": {"CAPTURED"},
    }
    with storage.get_store().engine.connect() as db:
        rows = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.payments)
                .where(
                    schema.payments.c.kind == "hold",
                    schema.payments.c.authorization_id.is_not(None),
                    schema.payments.c.status.in_(list(expected)),
                )
                .order_by(schema.payments.c.updated_at.desc())
                .limit(limit)
            )
        ]
    mismatches = []
    for payment in rows:
        try:
            remote = await pp.get_authorization(payment["authorization_id"])
        except PayPalError as exc:
            mismatches.append(
                {
                    "payment": payment["id"],
                    "ledger": payment["status"],
                    "paypal": exc.name or "error",
                }
            )
            continue
        if remote not in expected[payment["status"]] and not (
            payment["status"] == "CAPTURED" and remote in {"PARTIALLY_CAPTURED", "CAPTURED"}
        ):
            mismatches.append(
                {"payment": payment["id"], "ledger": payment["status"], "paypal": remote}
            )
    if mismatches:
        audit.record("system", "reconcile.mismatch", "", f"{len(mismatches)} payments differ")
    return {"checked": len(rows), "mismatches": mismatches}
