"""Seller onboarding, console, orders and disputes."""

from __future__ import annotations

import re
import secrets
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from maxx import audit
from maxx.auth import mail, ratelimit
from maxx.auth import store as accounts
from maxx.auth.deps import CurrentUser, FreshUser, same_origin
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.money import service as money
from maxx.negotiate.contracts import Money
from maxx.negotiate.routes import RuntimeDep
from maxx.sellers import rules, store

router = APIRouter(prefix="/seller", dependencies=[Depends(same_origin)])

CODE_TTL = 600
PURPOSE = "seller_payout_code"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
PHONE = re.compile(r"^[+()\d\s.-]{6,30}$")
TRACKING = re.compile(r"^[A-Za-z0-9 ._/-]{3,80}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL.match(value) or len(value) > 320:
        raise ValueError("Enter a valid email address.")
    return value


def _countries(values: list[str]) -> list[str]:
    cleaned = sorted({v.strip().upper() for v in values})
    if not cleaned or any(c not in rules.COUNTRIES for c in cleaned):
        raise ValueError("Choose the countries you ship to from the list.")
    return cleaned


class Apply(Strict):
    business_name: str = Field(min_length=2, max_length=120)
    legal_name: str = Field(min_length=2, max_length=160)
    business_type: str = Field(pattern="^(individual|company)$")
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    address_line1: str = Field(min_length=3, max_length=200)
    address_city: str = Field(min_length=1, max_length=100)
    address_region: str = Field(default="", max_length=100)
    address_postal: str = Field(min_length=2, max_length=20)
    phone: str = Field(max_length=40)
    support_email: str = Field(max_length=320)
    website: str = Field(default="", max_length=300)
    trade_register_no: str = Field(default="", max_length=60)
    payout_email: str = Field(max_length=320)
    ship_within_days: int = Field(ge=1, le=14)
    ships_to: list[str] = Field(min_length=1, max_length=30)
    return_days: int = Field(ge=rules.MIN_RETURN_DAYS, le=90)
    return_policy: str = Field(min_length=20, max_length=1000)
    accept_terms: bool
    certify_accurate: bool
    certify_lawful: bool
    certify_authorised: bool

    _emails = field_validator("support_email", "payout_email")(lambda value: _email(value))
    _ships = field_validator("ships_to")(lambda value: _countries(value))

    @field_validator("country")
    @classmethod
    def _country(cls, value: str) -> str:
        value = value.upper()
        if value not in rules.COUNTRIES:
            raise ValueError("We cannot onboard sellers from that country yet.")
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        if not PHONE.match(value):
            raise ValueError("Enter a phone number with digits, spaces, + ( ) - only.")
        return value

    @field_validator("website")
    @classmethod
    def _website(cls, value: str) -> str:
        if value and not re.match(r"^https://[^\s/]+\.[^\s/]{2,}(/\S*)?$", value):
            raise ValueError("The website must start with https://")
        return value

    @model_validator(mode="after")
    def _company_has_register(self):
        if (
            self.country in rules.EU
            and self.business_type == "company"
            and not self.trade_register_no
        ):
            raise ValueError("Companies in the EU must give their trade register number.")
        return self


class Commitments(Strict):
    """What a seller may change later without a new review."""

    ship_within_days: int = Field(ge=1, le=14)
    ships_to: list[str] = Field(min_length=1, max_length=30)
    return_days: int = Field(ge=rules.MIN_RETURN_DAYS, le=90)
    return_policy: str = Field(min_length=20, max_length=1000)
    support_email: str = Field(max_length=320)
    phone: str = Field(max_length=40)
    website: str = Field(default="", max_length=300)

    _email_ok = field_validator("support_email")(lambda value: _email(value))
    _ships = field_validator("ships_to")(lambda value: _countries(value))
    _phone = field_validator("phone")(Apply._phone.__func__)
    _site = field_validator("website")(Apply._website.__func__)


class PayoutEmail(Strict):
    payout_email: str = Field(max_length=320)

    _check = field_validator("payout_email")(lambda value: _email(value))


class Code(Strict):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OfferIn(Strict):
    product_key: str = Field(min_length=1, max_length=300)
    stock: int = Field(ge=1, le=100000)
    floor: Money
    opening_price: Money
    strategy: str = Field(pattern="^(firm|balanced|eager)$")


class Active(Strict):
    active: bool


class Ship(Strict):
    carrier: str = Field(min_length=2, max_length=40)
    tracking: str = Field(max_length=80)

    @field_validator("tracking")
    @classmethod
    def _tracking(cls, value: str) -> str:
        if not TRACKING.match(value):
            raise ValueError("Enter the tracking number (letters, digits, spaces, - . / _).")
        return value.strip()


class Reply(Strict):
    body: str = Field(min_length=2, max_length=2000)


def _profile(seller: dict | None) -> dict | None:
    if not seller:
        return None
    return {
        "code": seller["code"],
        "business_name": seller["business_name"],
        "legal_name": seller["legal_name"],
        "business_type": seller["business_type"],
        "country": seller["country"],
        "payout_email": store.mask_email(seller["payout_email"]),
        "payout_verified": bool(seller["payout_verified"]),
        "status": seller["status"],
        "review_note": seller["review_note"],
        "ship_within_days": seller["ship_within_days"],
        "ships_to": [c for c in seller["ships_to"].split(",") if c],
        "return_days": seller["return_days"],
        "return_policy": seller["return_policy"],
        "support_email": seller["support_email"],
        "phone": seller["phone"],
        "website": seller["website"],
        "strikes": seller["strikes"],
        "owed": str(orders.owed_by(seller["code"])),
    }


def _active_seller(user) -> dict:
    seller = store.by_user(user.id)
    if not seller:
        raise HTTPException(409, "Apply to sell first.")
    if seller["status"] == "SUSPENDED":
        raise HTTPException(403, "This seller account is suspended.")
    if seller["status"] == "REJECTED":
        raise HTTPException(403, "This application was not approved.")
    if seller["status"] == "UNDER_REVIEW":
        raise HTTPException(409, "Your application is under review.")
    if seller["status"] != "ACTIVE" or not seller["payout_verified"]:
        raise HTTPException(409, "Verify your payout email first.")
    return seller


async def _send_code(user, address: str) -> None:
    code = f"{secrets.randbelow(10**6):06d}"
    accounts.issue_custom_token(user.id, PURPOSE, address, f"{user.id}:{code}", CODE_TTL)
    await mail.send_code(address, user.display_name, code)


def _offer(row: dict) -> dict:
    return {
        "id": row["id"],
        "product_key": row["product_key"],
        "title": row["title"],
        "stock": row["stock"],
        "floor": str(row["floor"]),
        "opening_price": str(row["opening_price"]),
        "strategy": row["strategy"],
        "active": bool(row["active"]),
    }


@router.get("")
def overview(user: CurrentUser):
    seller = store.by_user(user.id)
    return {
        "seller": _profile(seller),
        "terms": rules.TERMS,
        "terms_version": rules.TERMS_VERSION,
        "prohibited": rules.PROHIBITED,
        "countries": sorted(rules.COUNTRIES),
        "eu_countries": sorted(rules.EU),
        "min_return_days": rules.MIN_RETURN_DAYS,
        "fee_percent": settings.platform_fee_percent,
        "review": settings.seller_review,
        "email_verified": user.email_verified,
        "strategies": {
            k: {"concession_percent": str(v[0] * 100)} for k, v in store.STRATEGIES.items()
        },
        "payments": money.enabled(),
    }


@router.post("/apply", status_code=201)
async def apply(body: Apply, user: CurrentUser):
    if not user.email_verified:
        raise HTTPException(403, "Verify your account email before you apply to sell.")
    if not (
        body.accept_terms
        and body.certify_accurate
        and body.certify_lawful
        and body.certify_authorised
    ):
        raise HTTPException(422, "Accept the seller agreement and every certification to continue.")
    ratelimit.hit(f"seller-apply:{user.id}", 5, 3600)
    if store.by_user(user.id):
        raise HTTPException(409, "You already applied. Open the seller console.")
    profile = body.model_dump(
        exclude={"accept_terms", "certify_accurate", "certify_lawful", "certify_authorised"}
    )
    profile["ships_to"] = ",".join(profile["ships_to"])
    profile["business_name"] = profile["business_name"].strip()
    profile["terms_version"] = rules.TERMS_VERSION
    seller = store.create(user.id, profile)
    await _send_code(user, seller["payout_email"])
    audit.record(f"user:{user.id[:8]}", "seller.applied", seller["code"], seller["country"])
    return _profile(seller)


@router.post("/payout-code", status_code=202)
async def resend_code(user: CurrentUser):
    seller = store.by_user(user.id)
    if not seller or seller["payout_verified"]:
        raise HTTPException(409, "There is no payout email waiting for verification.")
    ratelimit.hit(f"seller-code:{user.id}", 5, 3600)
    await _send_code(user, seller["payout_email"])
    return {"status": "sent"}


@router.post("/payout-verify")
def verify_payout(body: Code, user: CurrentUser):
    ratelimit.hit(f"seller-verify:{user.id}", 8, 3600)
    seller = store.by_user(user.id)
    if not seller:
        raise HTTPException(409, "Apply to sell first.")
    if seller["status"] in {"SUSPENDED", "REJECTED"}:
        raise HTTPException(403, "This seller account cannot be activated.")
    used = accounts.consume_token(f"{user.id}:{body.code}", PURPOSE)
    if used is None or used[1] != seller["payout_email"]:
        raise HTTPException(400, "That code is wrong or expired.")
    # In manual review the seller waits for an administrator; otherwise they are live.
    status = (
        "ACTIVE" if settings.seller_review == "auto" or seller["reviewed_at"] else "UNDER_REVIEW"
    )
    store.update_seller(
        seller["id"], payout_verified=True, payout_verified_at=int(time.time()), status=status
    )
    audit.record(f"user:{user.id[:8]}", "seller.payout_verified", seller["code"], status)
    return _profile(store.by_user(user.id))


@router.post("/payout-email", status_code=202)
async def change_payout_email(body: PayoutEmail, user: FreshUser):
    """Where the money goes is the most sensitive field, so it needs a fresh identity check and a
    new code. Until the new address is confirmed the seller sits out of Blocs and is not paid."""
    seller = store.by_user(user.id)
    if not seller:
        raise HTTPException(409, "Apply to sell first.")
    if seller["status"] in {"SUSPENDED", "REJECTED"}:
        raise HTTPException(403, "This seller account is suspended.")
    ratelimit.hit(f"seller-code:{user.id}", 5, 3600)
    store.update_seller(
        seller["id"],
        payout_email=body.payout_email,
        payout_verified=False,
        payout_verified_at=None,
        status="PENDING",
    )
    await _send_code(user, body.payout_email)
    audit.record(f"user:{user.id[:8]}", "seller.payout_email_changed", seller["code"])
    return _profile(store.by_user(user.id))


@router.post("/commitments")
def update_commitments(body: Commitments, user: CurrentUser):
    seller = store.by_user(user.id)
    if not seller or seller["status"] in {"SUSPENDED", "REJECTED"}:
        raise HTTPException(403, "This seller account cannot be changed.")
    ratelimit.hit(f"seller-commit:{user.id}", 20, 3600)
    store.update_seller(
        seller["id"],
        ship_within_days=body.ship_within_days,
        ships_to=",".join(body.ships_to),
        return_days=body.return_days,
        return_policy=body.return_policy,
        support_email=body.support_email,
        phone=body.phone,
        website=body.website,
    )
    audit.record(f"seller:{seller['code']}", "seller.commitments", seller["code"])
    return _profile(store.by_user(user.id))


def _demand(bloc) -> dict:
    held = sorted((m.max_price for m in bloc.members if m.status == "HELD"), reverse=True)
    points = []
    if held:
        low, high = held[-1], held[0]
        steps = 5
        for i in range(steps):
            price = (low + (high - low) * i / (steps - 1)).quantize(Decimal("0.01"))
            points.append({"price": str(price), "buyers": sum(m >= price for m in held)})
    median = str(held[len(held) // 2]) if held else None
    return {"buyers": len(held), "median_max": median, "curve": points}


@router.get("/opportunities")
def opportunities(user: CurrentUser, runtime: RuntimeDep):
    seller = _active_seller(user)
    mine = {o["product_key"]: o for o in store.offers_for(seller["id"])}
    now = int(time.time())
    seen: dict[str, dict] = {}
    for bloc in runtime.store.list_open():
        if bloc.closes_at and bloc.closes_at <= now:
            continue
        demand = _demand(bloc)
        if demand["buyers"] == 0:
            continue
        current = seen.get(bloc.product_key)
        if current and current["buyers"] >= demand["buyers"]:
            continue
        seen[bloc.product_key] = {
            "bloc_id": bloc.id,
            "product_key": bloc.product_key,
            "title": bloc.title,
            "typical_price": str(bloc.typical_price),
            "closes_at": bloc.closes_at,
            "my_offer": _offer(mine[bloc.product_key]) if bloc.product_key in mine else None,
            **demand,
        }
    return sorted(seen.values(), key=lambda row: -row["buyers"])


@router.get("/offers")
def my_offers(user: CurrentUser):
    seller = _active_seller(user)
    return [_offer(o) for o in store.offers_for(seller["id"])]


@router.post("/offers")
def save_offer(body: OfferIn, user: CurrentUser, runtime: RuntimeDep):
    seller = _active_seller(user)
    if body.opening_price < body.floor:
        raise HTTPException(422, "Your opening price must be at or above your floor.")
    known = runtime.store.find_by_product(body.product_key)
    if known is None:
        raise HTTPException(404, "No Bloc exists for that product yet.")
    if body.floor > known.typical_price * 2:
        raise HTTPException(422, "That floor is far above the product's typical price.")
    ratelimit.hit(f"seller-offer:{user.id}", 60, 3600)
    row = store.upsert_offer(
        seller["id"],
        body.product_key,
        known.title,
        body.stock,
        body.floor,
        body.opening_price,
        body.strategy,
    )
    audit.record(f"seller:{seller['code']}", "offer.saved", row["id"], known.title[:60])
    return _offer(row)


@router.post("/offers/{offer_id}/active")
def toggle_offer(offer_id: str, body: Active, user: CurrentUser):
    seller = _active_seller(user)
    if not store.set_active(seller["id"], offer_id, body.active):
        raise HTTPException(404, "Offer not found.")
    return _offer(store.get_offer(seller["id"], offer_id))


@router.get("/results")
def results(user: CurrentUser, runtime: RuntimeDep):
    """What happened to this seller's offers, and the money. No buyer is identifiable here."""
    seller = _active_seller(user)
    code = seller["code"]
    payouts: dict[tuple, list[dict]] = {}
    for row in _payouts(code):
        payouts.setdefault((row["bloc_id"], row["generation"]), []).append(row)
    out = []
    for bloc in runtime.store.list_with_seller(code):
        wins = [
            a for a in (bloc.outcome.allocations if bloc.outcome else []) if a.seller_id == code
        ]
        rows = payouts.get((bloc.id, bloc.generation), [])
        paid = [r for r in rows if r["status"] in {"SENT", "OFFSET"}]
        out.append(
            {
                "bloc_id": bloc.id,
                "title": bloc.title,
                "status": bloc.status,
                "units": len(wins),
                "paid_units": sum(r["units"] for r in rows),
                "average_price": str(
                    (sum(a.price for a in wins) / len(wins)).quantize(Decimal("0.01"))
                )
                if wins
                else None,
                "payout": {
                    "gross": str(sum(Decimal(r["gross_amount"]) for r in rows)),
                    "fee": str(sum(Decimal(r["fee_amount"]) for r in rows)),
                    "net": str(sum(Decimal(r["net_amount"]) for r in paid)),
                    "status": "SENT" if rows and len(paid) == len(rows) else "PENDING",
                    "simulated": bool(rows[0]["simulated"]),
                }
                if rows
                else None,
            }
        )
    return out


def _payouts(code: str) -> list[dict]:
    from sqlalchemy import select

    from maxx import schema, storage

    with storage.get_store().engine.connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(select(schema.payouts).where(schema.payouts.c.seller_id == code))
        ]


# ---- orders to ship ------------------------------------------------------------------------------


def _order_for_seller(order: dict, with_address: bool) -> dict:
    case = orders.open_case_for(order["id"])
    fee = (Decimal(order["amount"]) * Decimal(settings.platform_fee_percent) / 100).quantize(
        Decimal("0.01")
    )
    view = {
        "id": order["id"],
        "title": order["title"],
        "amount": str(order["amount"]),
        "your_share": str(Decimal(order["amount"]) - fee),
        "status": order["status"],
        "ship_by": order["ship_by"],
        "carrier": order["carrier"],
        "tracking": order["tracking"],
        "created_at": order["created_at"],
        "case_id": case["id"] if case else None,
        "address": None,
    }
    if with_address and order["status"] in {"AWAITING_SHIPMENT", "SHIPPED"}:
        view["address"] = orders.read_blob(order["address_blob"])
    return view


@router.get("/orders")
def seller_orders(user: CurrentUser):
    seller = _active_seller(user)
    return [
        _order_for_seller(o, True)
        for o in orders.orders_where(seller_user_id=user.id)
        if o["seller_code"] == seller["code"]
    ]


@router.post("/orders/{order_id}/ship")
async def ship_order(order_id: str, body: Ship, user: CurrentUser):
    _active_seller(user)
    ratelimit.hit(f"seller-ship:{user.id}", 120, 3600)
    try:
        order = await fulfilment.ship(user.id, order_id, body.carrier.strip(), body.tracking)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except fulfilment.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return _order_for_seller(order, True)


def _case_view(case: dict, order: dict) -> dict:
    return {
        "id": case["id"],
        "order_id": order["id"],
        "title": order["title"],
        "amount": str(order["amount"]),
        "kind": case["kind"],
        "status": case["status"],
        "opened_at": case["opened_at"],
        "respond_by": case["respond_by"],
        "resolution": case["resolution"],
        "messages": [
            {"actor": e["actor"], "body": e["body"], "at": e["created_at"]}
            for e in orders.events_for(case["id"])
        ],
    }


@router.get("/cases")
def seller_cases(user: CurrentUser):
    _active_seller(user)
    mine = orders.orders_where(seller_user_id=user.id)
    by_id = {o["id"]: o for o in mine}
    return [_case_view(c, by_id[c["order_id"]]) for c in orders.cases_for_orders(list(by_id))]


@router.post("/cases/{case_id}/reply")
def reply_case(case_id: str, body: Reply, user: CurrentUser):
    _active_seller(user)
    ratelimit.hit(f"case-msg:{user.id}", 60, 3600)
    try:
        fulfilment.post_message(user.id, case_id, body.body)
    except LookupError:
        raise HTTPException(404, "Case not found.") from None
    except fulfilment.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": "sent"}


@router.post("/cases/{case_id}/refund")
async def agree_refund(case_id: str, user: CurrentUser):
    seller = _active_seller(user)
    case = orders.get_case(case_id)
    order = orders.get_order(case["order_id"]) if case else None
    if not order or order["seller_user_id"] != user.id:
        raise HTTPException(404, "Case not found.")
    try:
        done = await fulfilment.resolve_case(
            case_id, True, f"seller:{seller['code']}", "The seller agreed to refund."
        )
    except fulfilment.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return _case_view(done, orders.get_order(order["id"]))
