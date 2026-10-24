"""Operator console: seller review, disputes, payment health and the emergency brake."""

from __future__ import annotations

import json
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from maxx import audit, budget, schema, storage
from maxx.auth.deps import CurrentUser, FreshUser, is_admin, same_origin
from maxx.compliance import sanctions
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.negotiate.routes import RuntimeDep
from maxx.notify import service as notify
from maxx.sellers import lifecycle
from maxx.sellers import store as sellers


async def require_admin(user: CurrentUser):
    if not is_admin(user):
        raise HTTPException(403, "Administrators only.")
    return user


router = APIRouter(prefix="/admin", dependencies=[Depends(same_origin), Depends(require_admin)])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(Strict):
    action: str = Field(pattern="^(approve|reject|suspend|reinstate)$")
    note: str = Field(default="", max_length=500)


class Resolve(Strict):
    refund: bool
    note: str = Field(min_length=3, max_length=500)


class Freeze(Strict):
    frozen: bool


class PauseAi(Strict):
    paused: bool


def ai_activity(hours: int = 24) -> dict:
    """Model calls, refusals and guard hits per role over the last day, from the call log."""
    since = time.time_ns() - hours * 3600 * 10**9
    with storage.get_store().engine.connect() as db:
        rows = db.execute(
            select(schema.calls.c.metadata)
            .where(schema.calls.c.created_at >= since)
            .order_by(schema.calls.c.created_at.desc())
            .limit(20000)
        ).scalars()
        records = [json.loads(r) for r in rows]
    roles: dict[str, dict] = {}
    guards: dict[str, int] = {}
    for record in records:
        for rule in record.get("guard") or []:
            guards[rule] = guards.get(rule, 0) + 1
        if record.get("provider") == "guard":
            continue
        role = roles.setdefault(
            str(record.get("purpose")), {"calls": 0, "refused": 0, "rejected": 0, "cost_usd": "0"}
        )
        status = record.get("status")
        role["calls" if status not in {"refused"} else "refused"] += 1
        role["rejected"] += status == "rejected"
        if record.get("cost_usd"):
            role["cost_usd"] = str(Decimal(role["cost_usd"]) + Decimal(record["cost_usd"]))
    return {"roles": roles, "guards": guards}


class Screening(Strict):
    decision: str = Field(pattern="^(clear|block)$")
    note: str = Field(min_length=3, max_length=500)


class Takedown(Strict):
    note: str = Field(min_length=3, max_length=500)


class ClearFlag(Strict):
    note: str = Field(min_length=3, max_length=500)


def _seller_row(seller: dict) -> dict:
    keys = (
        "code business_name legal_name business_type country address_line1 address_city "
        "address_region address_postal phone support_email website trade_register_no "
        "ship_within_days ships_to return_days return_policy status review_note strikes "
        "payout_verified created_at identity_status identity_name identity_country "
        "screening_status tax_id_last4 demo"
    ).split()
    return {k: seller[k] for k in keys} | {
        "payout_email": sellers.mask_email(seller["payout_email"]),
        "screening_hits": json.loads(seller["screening_hits"] or "[]"),
        "next_step": lifecycle.next_step(seller),
    }


@router.get("/overview")
def overview():
    with storage.get_store().engine.connect() as db:
        pending = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.sellers).where(schema.sellers.c.status == "UNDER_REVIEW")
            )
        ]
        recent = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.sellers).order_by(schema.sellers.c.created_at.desc()).limit(20)
            )
        ]
        failed_payouts = db.execute(
            select(func.count()).where(schema.payouts.c.status == "FAILED")
        ).scalar()
        stuck = db.execute(
            select(func.count()).where(
                schema.payments.c.kind == "hold",
                schema.payments.c.status.in_(["VOID_PENDING", "CAPTURE_FAILED"]),
            )
        ).scalar()
        partial = db.execute(
            select(func.count()).where(schema.settlements.c.status == "PARTIAL")
        ).scalar()
    cases = [
        {
            "id": c["id"],
            "order_id": c["order_id"],
            "kind": c["kind"],
            "opened_at": c["opened_at"],
            "respond_by": c["respond_by"],
            "overdue": time.time() > c["respond_by"],
            "messages": [
                {"actor": e["actor"], "body": e["body"], "at": e["created_at"]}
                for e in orders.events_for(c["id"])
            ],
        }
        for c in orders.all_open_cases()
    ]
    flagged = [
        {
            "id": o["id"],
            "title": o["title"],
            "seller": o["seller_code"],
            "status": o["status"],
            "carrier": o["carrier"],
            "tracking_status": o["tracking_status"],
            "flag": o["review_flag"],
        }
        for o in orders.orders_in(["SHIPPED", "DELIVERED"])
        if fulfilment.flagged(o)
    ]
    age = sanctions.age_seconds()
    return {
        "payments_frozen": audit.payments_frozen(),
        "mode": settings.paypal_mode,
        "review_mode": settings.seller_review,
        "modes": {
            "tracking": settings.tracking_mode,
            "identity": settings.verify_mode,
            "negotiation": settings.negotiation_mode,
        },
        "health": {
            "failed_payouts": failed_payouts,
            "stuck_payments": stuck,
            "partial_settlements": partial,
            "orders_awaiting_shipment": len(orders.orders_in(["AWAITING_SHIPMENT"])),
            "orders_awaiting_address": len(orders.orders_in(["AWAITING_ADDRESS"])),
            "flagged_shipments": len(flagged),
            "email_outbox": notify.outbox_health(),
            "sanctions_list_age_hours": round(age / 3600, 1) if age is not None else None,
        },
        "pending_sellers": [_seller_row(s) for s in pending],
        "recent_sellers": [_seller_row(s) for s in recent],
        "open_cases": cases,
        "flagged_orders": flagged,
        "listings": [
            {
                "id": row["id"],
                "title": row["title"],
                "seller": row["code"],
                "seller_name": row["business_name"],
                "gtin": row["gtin"],
                "category": row["category"],
                "active": bool(row["active"]),
                "created_at": row["created_at"],
            }
            for row in sellers.listings()
        ],
        "audit": audit.recent(60),
        "ai": ai_overview(),
    }


@router.post("/sellers/{code}/decision")
def decide(code: str, body: Decision, user: FreshUser):
    seller = sellers.by_code(code)
    if not seller:
        raise HTTPException(404, "Seller not found.")
    now = int(time.time())
    fields: dict = {"review_note": body.note, "reviewed_at": now, "reviewed_by": user.id}
    if body.action == "approve":
        if seller["status"] != "UNDER_REVIEW" or not seller["payout_verified"]:
            raise HTTPException(409, "Only a verified application under review can be approved.")
        if seller["screening_status"] in {"review", "blocked", "pending"}:
            raise HTTPException(409, "Resolve the sanctions screening before approving.")
    elif body.action == "reject":
        if seller["status"] not in {"UNDER_REVIEW", "PENDING"}:
            raise HTTPException(409, "Only a pending application can be rejected.")
        fields["status"] = "REJECTED"
    elif body.action == "suspend":
        fields["status"] = "SUSPENDED"
    else:  # reinstate
        if seller["status"] != "SUSPENDED":
            raise HTTPException(409, "Only a suspended seller can be reinstated.")
        if seller["screening_status"] == "blocked":
            raise HTTPException(409, "A seller blocked by sanctions screening stays suspended.")
        fields.update(status="PENDING", strikes=0)
    sellers.update_seller(seller["id"], **fields)
    audit.record(f"admin:{user.id[:8]}", f"seller.{body.action}", code, body.note[:200])
    fresh = lifecycle.evaluate(seller["id"])
    if body.action in {"reject", "suspend"}:
        notify.notify(
            seller["user_id"],
            "seller.status",
            "Your seller application was not approved"
            if body.action == "reject"
            else "Your seller account is suspended",
            "Your offers no longer join Blocs. Orders you already have must still be shipped "
            "and supported. Reply to Maxx support if you think this is a mistake.",
            "/sell",
        )
    return _seller_row(fresh)


@router.post("/sellers/{code}/screening")
async def decide_screening(code: str, body: Screening, user: FreshUser, runtime: RuntimeDep):
    """A person's decision on possible sanctions matches. Clearing marks the current matches as
    reviewed (a new match later is reviewed again); blocking suspends the seller for good."""
    seller = sellers.by_code(code)
    if not seller:
        raise HTTPException(404, "Seller not found.")
    if seller["screening_status"] not in {"review", "blocked"}:
        raise HTTPException(409, "There is nothing to review for this seller.")
    hits = json.loads(seller["screening_hits"] or "[]")
    if body.decision == "clear":
        for hit in hits:
            hit["cleared"] = True
        sellers.update_seller(
            seller["id"], screening_status="clear", screening_hits=json.dumps(hits)
        )
    else:
        sellers.update_seller(
            seller["id"],
            screening_status="blocked",
            status="SUSPENDED",
            review_note="Your account cannot be used. Contact Maxx support.",
        )
        await _end_listings(
            runtime, seller, "The seller can no longer sell. Every hold is released."
        )
    audit.record(f"admin:{user.id[:8]}", f"screening.{body.decision}", code, body.note[:200])
    return _seller_row(lifecycle.evaluate(seller["id"]))


async def _fail_listing_bloc(runtime, product_key: str, reason: str) -> int:
    """End an open listing Bloc so every buyer's hold is released by the settlement worker."""
    from maxx.negotiate.runner import terminal_failure

    ended = 0
    async with runtime.lock:
        for bloc in runtime.store.list_open():
            if bloc.product_key == product_key and bloc.origin == "listing":
                terminal_failure(bloc, reason)
                runtime.store.save(bloc)
                ended += 1
    return ended


async def _end_listings(runtime, seller: dict, reason: str) -> None:
    for offer in sellers.offers_for(seller["id"]):
        if offer["active"]:
            sellers.set_active(seller["id"], offer["id"], False)
        if offer["listing"]:
            await _fail_listing_bloc(runtime, offer["product_key"], reason)


@router.post("/listings/{offer_id}/takedown")
async def takedown(offer_id: str, body: Takedown, user: FreshUser, runtime: RuntimeDep):
    offer = sellers.offer_by_id(offer_id)
    if not offer or not offer["listing"]:
        raise HTTPException(404, "Listing not found.")
    sellers.set_active(offer["seller_id"], offer_id, False)
    ended = await _fail_listing_bloc(
        runtime, offer["product_key"], "The listing was removed. Every hold is released."
    )
    seller = sellers.by_id(offer["seller_id"])
    audit.record(f"admin:{user.id[:8]}", "listing.takedown", offer_id, body.note[:200])
    if seller:
        notify.notify(
            seller["user_id"],
            "seller.listing",
            f"Your listing was removed: {notify.safe_text(offer['title'])}",
            "It broke the listing rules. Buyers' holds are released. Reply to Maxx support if "
            "you think this is a mistake.",
            "/sell",
        )
    return {"ended_blocs": ended}


@router.post("/orders/{order_id}/clear-flag")
async def clear_flag(order_id: str, body: ClearFlag, user: FreshUser):
    """A person checked a flagged shipment (for example with the carrier) and releases it."""
    order = orders.get_order(order_id)
    if not order or not fulfilment.flagged(order):
        raise HTTPException(404, "No flagged order with that id.")
    orders.update_order(order_id, None, review_flag=(fulfilment.CLEARED + body.note)[:120])
    audit.record(f"admin:{user.id[:8]}", "order.flag_cleared", order_id, body.note[:200])
    status = await fulfilment.release_payout(order_id)
    return {"payout": status}


@router.post("/cases/{case_id}/resolve")
async def resolve(case_id: str, body: Resolve, user: CurrentUser):
    try:
        case = await fulfilment.resolve_case(
            case_id, body.refund, f"admin:{user.id[:8]}", body.note
        )
    except LookupError:
        raise HTTPException(404, "Case not found.") from None
    except fulfilment.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return {"id": case["id"], "status": case["status"]}


@router.post("/payments/freeze")
def freeze(body: Freeze, user: FreshUser):
    """The emergency brake: no new holds, captures or payouts while frozen. Holds stay safe."""
    audit.set_flag("payments_frozen", "1" if body.frozen else "0")
    audit.record(
        f"admin:{user.id[:8]}", "payments.freeze", "", "frozen" if body.frozen else "thawed"
    )
    return {"payments_frozen": audit.payments_frozen()}


def ai_overview() -> dict:
    status = budget.status()
    return {"paused": status.pop("paused"), "budget": status, **ai_activity()}


@router.post("/ai/pause")
def pause_ai(body: PauseAi, user: FreshUser):
    """The AI kill switch: every live model and search call is refused while paused."""
    audit.set_flag("ai_paused", "1" if body.paused else "0")
    audit.record(f"admin:{user.id[:8]}", "ai.pause", "", "paused" if body.paused else "resumed")
    return {"ai_paused": budget.status()["paused"]}


@router.get("/audit")
def audit_trail(limit: int = 100, prefix: str = ""):
    return audit.recent(min(max(limit, 1), 500), prefix[:20])


@router.get("/reconcile")
async def reconcile_remote():
    """Compare the ledger with PayPal for recent holds. Read-only."""
    from maxx.money import service

    return await service.verify_remote()
