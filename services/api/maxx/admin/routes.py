"""Operator console: seller review, disputes, payment health and the emergency brake."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from maxx import audit, schema, storage
from maxx.auth.deps import CurrentUser, FreshUser, is_admin, same_origin
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
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


def _seller_row(seller: dict) -> dict:
    keys = (
        "code business_name legal_name business_type country address_line1 address_city "
        "address_region address_postal phone support_email website trade_register_no "
        "ship_within_days ships_to return_days return_policy status review_note strikes "
        "payout_verified created_at"
    ).split()
    return {k: seller[k] for k in keys} | {
        "payout_email": sellers.mask_email(seller["payout_email"])
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
    return {
        "payments_frozen": audit.payments_frozen(),
        "mode": settings.paypal_mode,
        "review_mode": settings.seller_review,
        "health": {
            "failed_payouts": failed_payouts,
            "stuck_payments": stuck,
            "partial_settlements": partial,
            "orders_awaiting_shipment": len(orders.orders_in(["AWAITING_SHIPMENT"])),
            "orders_awaiting_address": len(orders.orders_in(["AWAITING_ADDRESS"])),
        },
        "pending_sellers": [_seller_row(s) for s in pending],
        "recent_sellers": [_seller_row(s) for s in recent],
        "open_cases": cases,
        "audit": audit.recent(60),
    }


@router.post("/sellers/{code}/decision")
def decide(code: str, body: Decision, user: CurrentUser):
    seller = sellers.by_code(code)
    if not seller:
        raise HTTPException(404, "Seller not found.")
    now = int(time.time())
    fields: dict = {"review_note": body.note, "reviewed_at": now, "reviewed_by": user.id}
    if body.action == "approve":
        if seller["status"] != "UNDER_REVIEW" or not seller["payout_verified"]:
            raise HTTPException(409, "Only a verified application under review can be approved.")
        fields["status"] = "ACTIVE"
    elif body.action == "reject":
        if seller["status"] not in {"UNDER_REVIEW", "PENDING"}:
            raise HTTPException(409, "Only a pending application can be rejected.")
        fields["status"] = "REJECTED"
    elif body.action == "suspend":
        fields["status"] = "SUSPENDED"
    else:  # reinstate
        if seller["status"] != "SUSPENDED":
            raise HTTPException(409, "Only a suspended seller can be reinstated.")
        fields.update(status="ACTIVE" if seller["payout_verified"] else "PENDING", strikes=0)
    sellers.update_seller(seller["id"], **fields)
    audit.record(f"admin:{user.id[:8]}", f"seller.{body.action}", code, body.note[:200])
    return _seller_row(sellers.by_code(code))


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


@router.get("/audit")
def audit_trail(limit: int = 100, prefix: str = ""):
    return audit.recent(min(max(limit, 1), 500), prefix[:20])


@router.get("/reconcile")
async def reconcile_remote():
    """Compare the ledger with PayPal for recent holds. Read-only."""
    from maxx.money import service

    return await service.verify_remote()
