"""Where a seller is on the way from applying to selling, decided in one place.

A seller is ACTIVE only when every step is done:
  1. the payout email is confirmed with a code;
  2. their identity is verified by the provider (when SELLER_IDENTITY_REQUIRED and VERIFY_MODE
     is on);
  3. their names are screened against the OFAC sanctions lists and either nothing matched or a
     person cleared the match;
  4. an administrator approved them (SELLER_REVIEW=manual, required in production).

Until then they are PENDING (a step is theirs to do) or UNDER_REVIEW (Maxx is checking).
REJECTED, SUSPENDED and CLOSED are decisions and are never undone here.

Separately, `can_sell` answers whether an ACTIVE seller may take new sales: under the US INFORM
Consumers Act a high-volume seller must give a tax id within SELLER_INFO_DAYS, and every seller
re-certifies their details once a year; until they do, their offers sit out of new Blocs (orders
they already have are unaffected).
"""

from __future__ import annotations

import json
import logging
import re
import time
from decimal import Decimal

from sqlalchemy import func, select

from maxx import audit, schema, storage
from maxx.compliance import identity, sanctions
from maxx.config import settings
from maxx.notify.service import notify
from maxx.sellers import store

log = logging.getLogger(__name__)
DAY = 86400
YEAR = 365 * DAY
DECISIONS = {"REJECTED", "SUSPENDED", "CLOSED"}


def screen(seller: dict) -> str:
    """Screen the seller's names and record the outcome. Returns clear, review or pending."""
    if seller["screening_status"] == "blocked":
        return "blocked"
    names = [seller["legal_name"], seller["business_name"], seller["identity_name"]]
    try:
        hits = sanctions.screen([n for n in names if n])
    except RuntimeError:
        store.update_seller(seller["id"], screening_status="pending")
        return "pending"
    previous = json.loads(seller["screening_hits"] or "[]")
    cleared = {h["entry_id"] for h in previous if h.get("cleared")}
    fresh = [h.as_dict() for h in hits if h.entry_id not in cleared]
    status = "review" if fresh else "clear"
    store.update_seller(
        seller["id"],
        screening_status=status,
        screening_hits=json.dumps([*[h for h in previous if h.get("cleared")], *fresh]),
        screened_at=int(time.time()),
    )
    if fresh:
        audit.record("system", "seller.screening_match", seller["code"], f"{len(fresh)} names")
    return status


def next_step(seller: dict) -> str | None:
    """The first thing still missing before the seller can be ACTIVE, or None."""
    if not seller["payout_verified"]:
        return "payout_email"
    if identity.required() and seller["identity_status"] != "verified":
        return "identity"
    if seller["screening_status"] in {"pending", "review", "blocked"}:
        return "screening"
    if settings.seller_review == "manual" and not seller["reviewed_at"]:
        return "review"
    return None


def evaluate(seller_id_or_row) -> dict:
    """Recompute and store the seller's status. Returns the fresh row."""
    seller = (
        seller_id_or_row if isinstance(seller_id_or_row, dict) else store.by_id(seller_id_or_row)
    )
    if seller is None or seller["status"] in DECISIONS:
        return seller
    if seller["payout_verified"] and (
        seller["screened_at"] is None or seller["screening_status"] == "pending"
    ):
        screen(seller)
        seller = store.by_id(seller["id"])
    step = next_step(seller)
    status = {
        None: "ACTIVE",
        "payout_email": "PENDING",
        "identity": "PENDING",
        "screening": "UNDER_REVIEW",
        "review": "UNDER_REVIEW",
    }[step]
    if status != seller["status"]:
        fields: dict = {"status": status}
        if status == "ACTIVE" and not seller["recertify_by"]:
            fields["recertify_by"] = int(time.time()) + YEAR
        store.update_seller(seller["id"], **fields)
        audit.record("system", f"seller.{status.lower()}", seller["code"], step or "")
        if status == "ACTIVE":
            notify(
                seller["user_id"],
                "seller.status",
                "Your seller account is live",
                "You can publish listings and standing offers now. Your offers join every new "
                "Bloc for the product.",
                "/sell",
                f"seller-live:{seller['id']}:{seller['reviewed_at'] or 0}",
            )
            from maxx.fulfilment import service as fulfilment

            fulfilment.retry_failed_payouts(seller["code"])
        elif step == "screening" and seller["status"] == "ACTIVE":
            notify(
                seller["user_id"],
                "seller.status",
                "Your seller account needs a manual check",
                "A person at Maxx is reviewing your account. Your offers sit out of new Blocs "
                "until then; orders you already have are unaffected.",
                "/sell",
            )
    return store.by_id(seller["id"])


def apply_identity(seller: dict, result: identity.Result) -> dict:
    """Record a provider's verdict on a seller's identity, then re-evaluate them."""
    if result.session_id != seller["identity_session"]:
        return seller
    fields: dict = {"identity_checked_at": int(time.time())}
    if result.status == "verified":
        fields.update(
            identity_status="verified",
            identity_name=result.name[:160],
            identity_country=result.country[:2],
        )
    elif result.status in {"requires_input", "canceled"}:
        fields["identity_status"] = "requires_input"
    else:
        fields["identity_status"] = "pending"
    changed = fields.get("identity_status") != seller["identity_status"]
    store.update_seller(seller["id"], **fields)
    if changed:
        audit.record("provider", f"seller.identity_{fields['identity_status']}", seller["code"])
        if fields["identity_status"] == "verified":
            # A new verified name is screened again, and an individual's must match the account.
            fresh = store.by_id(seller["id"])
            if (
                seller["business_type"] == "individual"
                and result.name
                and not names_match(result.name, seller["legal_name"])
            ):
                store.update_seller(
                    seller["id"],
                    screening_status="review",
                    screening_hits=json.dumps(
                        [
                            *json.loads(fresh["screening_hits"] or "[]"),
                            {
                                "entry_id": "name-mismatch",
                                "name": "The verified ID name differs from the legal name given",
                                "program": "",
                                "score": 0,
                            },
                        ]
                    ),
                )
            else:
                screen(fresh)
        notify(
            seller["user_id"],
            "seller.identity",
            "Identity verified"
            if fields["identity_status"] == "verified"
            else "Your identity check needs another try",
            "Thank you, your ID check is complete."
            if fields["identity_status"] == "verified"
            else "The provider could not verify your ID. Start the check again from your "
            "seller console, with a clear photo of a valid ID document.",
            "/sell",
        )
    return evaluate(seller["id"])


def names_match(verified: str, given: str) -> bool:
    a = set(sanctions.normalise(verified).split())
    b = set(sanctions.normalise(given).split())
    return bool(a and b) and len(a & b) >= min(2, len(a), len(b))


# ---- US INFORM Consumers Act -----------------------------------------------------------------


def sales_last_year(seller_code: str) -> tuple[int, Decimal]:
    since = int(time.time()) - YEAR
    o = schema.orders.c
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(func.count(), func.coalesce(func.sum(o.amount), 0)).where(
                o.seller_code == seller_code,
                o.created_at >= since,
                o.status.not_in(["CANCELLED", "REFUNDED"]),
            )
        ).first()
    return int(row[0] or 0), Decimal(row[1] or 0)


def high_volume(seller_code: str) -> bool:
    count, revenue = sales_last_year(seller_code)
    return count >= settings.high_volume_sales and revenue >= Decimal(settings.high_volume_revenue)


def can_sell(seller: dict, now: int | None = None) -> bool:
    """Whether an ACTIVE seller's offers may join new Blocs right now."""
    if seller["status"] != "ACTIVE" or not seller["payout_verified"]:
        return False
    now = now or int(time.time())
    if seller["info_due_by"] and now > seller["info_due_by"] and not seller["tax_id_last4"]:
        return False
    if seller["recertify_by"] and now > seller["recertify_by"] + settings.seller_info_days * DAY:
        return False
    return True


def compliance_view(seller: dict) -> dict:
    now = int(time.time())
    count, revenue = sales_last_year(seller["code"])
    return {
        "identity_status": seller["identity_status"],
        "identity_required": identity.required(),
        "identity_mode": settings.verify_mode,
        "next_step": next_step(seller),
        "can_sell": can_sell(seller),
        "high_volume": bool(seller["high_volume_since"]),
        "tax_id_on_file": bool(seller["tax_id_last4"]),
        "tax_id_last4": seller["tax_id_last4"],
        "info_due_by": seller["info_due_by"],
        "recertify_by": seller["recertify_by"],
        "recertify_due": bool(seller["recertify_by"] and now > seller["recertify_by"]),
        "sales_last_year": count,
        "revenue_last_year": str(revenue),
        "thresholds": {
            "sales": settings.high_volume_sales,
            "revenue": settings.high_volume_revenue,
            "days": settings.seller_info_days,
        },
    }


TAX_ID = re.compile(r"^[A-Za-z0-9 .-]{4,30}$")


def record_certification(seller: dict, tax_id: str | None) -> dict:
    from maxx import secrets as vault

    fields: dict = {"recertify_by": int(time.time()) + YEAR, "certified_at": int(time.time())}
    if tax_id:
        cleaned = re.sub(r"[\s.-]", "", tax_id)
        fields.update(
            tax_id_enc=vault.encrypt(cleaned, "seller-tax-id"),
            tax_id_last4=cleaned[-4:],
            info_due_by=None,
        )
    store.update_seller(seller["id"], **fields)
    audit.record(
        f"seller:{seller['code']}", "seller.certified", seller["code"], "tax id" if tax_id else ""
    )
    return store.by_id(seller["id"])


def sweep_compliance() -> dict:
    """Daily-ish: start INFORM deadlines for sellers who became high-volume, and remind sellers
    whose yearly re-certification is due. Re-screens sellers whose screening is pending."""
    done = {"high_volume": 0, "recertify": 0, "screened": 0}
    now = int(time.time())
    with storage.get_store().engine.connect() as db:
        rows = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.sellers).where(
                    schema.sellers.c.status.in_(["ACTIVE", "UNDER_REVIEW", "PENDING"])
                )
            )
        ]
    for seller in rows:
        if seller["screening_status"] == "pending" and sanctions.loaded():
            screen(seller)
            evaluate(seller["id"])
            done["screened"] += 1
        if seller["status"] != "ACTIVE":
            continue
        if not seller["high_volume_since"] and high_volume(seller["code"]):
            store.update_seller(
                seller["id"],
                high_volume_since=now,
                info_due_by=None
                if seller["tax_id_last4"]
                else now + settings.seller_info_days * DAY,
            )
            done["high_volume"] += 1
            if not seller["tax_id_last4"]:
                notify(
                    seller["user_id"],
                    "seller.info_required",
                    "Add your tax id to keep selling",
                    "You now count as a high-volume seller under US law (the INFORM Consumers "
                    f"Act). Add your tax id in your seller console within "
                    f"{settings.seller_info_days} days, or your offers pause until you do.",
                    "/sell",
                    f"inform:{seller['id']}",
                )
        due = seller["recertify_by"]
        if due and now > due - 14 * DAY:
            done["recertify"] += notify(
                seller["user_id"],
                "seller.info_required",
                "Confirm your seller details for this year",
                "Once a year sellers confirm their business details are still correct. It takes "
                "a minute in your seller console.",
                "/sell",
                f"recertify:{seller['id']}:{due}",
            )
    return done
