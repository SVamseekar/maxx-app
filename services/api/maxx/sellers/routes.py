"""Seller onboarding, verification, listings, console, orders and disputes."""

from __future__ import annotations

import re
import secrets
import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from maxx import audit, schema, storage
from maxx.auth import mail, ratelimit
from maxx.auth import store as accounts
from maxx.auth.deps import CurrentUser, FreshUser, client_ip, same_origin
from maxx.compliance import identity
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.fulfilment import tracking, tracking_numbers
from maxx.money import service as money
from maxx.negotiate.blocs import make_bloc
from maxx.negotiate.contracts import Money
from maxx.negotiate.routes import RuntimeDep
from maxx.sellers import catalog, lifecycle, rules, store

router = APIRouter(prefix="/seller", dependencies=[Depends(same_origin)])
# Called by the identity provider, not a browser, so no same-origin check; see compliance/identity.
hooks = APIRouter()

CODE_TTL = 600
PURPOSE = "seller_payout_code"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
PHONE = re.compile(r"^[+()\d\s.-]{6,30}$")


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


class Agent(Strict):
    strategy: str = Field(pattern="^(firm|balanced|eager)$")
    agent: str = Field(default="rules", pattern="^(rules|ai)$")
    guidance: str = Field(default="", max_length=280)

    @field_validator("guidance")
    @classmethod
    def _guidance(cls, value: str) -> str:
        from maxx.negotiate.adapters import clean_guidance

        return clean_guidance(value)


class OfferIn(Agent):
    product_key: str = Field(min_length=1, max_length=300)
    stock: int = Field(ge=1, le=100000)
    floor: Money
    opening_price: Money


class ListingIn(Agent):
    title: str = Field(min_length=8, max_length=160)
    gtin: str = Field(default="", max_length=20)
    category: str = Field(max_length=40)
    typical_price: Money
    stock: int = Field(ge=1, le=100000)
    floor: Money
    opening_price: Money

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 8:
            raise ValueError("Give the exact product: brand, model and variant.")
        return value


class Active(Strict):
    active: bool


class Ship(Strict):
    carrier: str = Field(max_length=20)
    tracking: str = Field(min_length=3, max_length=80)


class Reply(Strict):
    body: str = Field(min_length=2, max_length=2000)


class SimulatedCheck(Strict):
    session: str = Field(max_length=80)
    outcome: str = Field(pattern="^(verified|failed)$")


class Certify(Strict):
    certify: bool
    tax_id: str = Field(default="", max_length=30)

    @field_validator("tax_id")
    @classmethod
    def _tax(cls, value: str) -> str:
        value = value.strip()
        if value and not lifecycle.TAX_ID.match(value):
            raise ValueError("Enter the tax id with letters, digits, spaces, dots or dashes.")
        return value


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
        "demo": bool(seller["demo"]),
        "trusted": fulfilment.trusted(seller, seller["code"]),
        "deliveries": fulfilment.deliveries_by(seller["code"]),
        # Sanctions details are never shown to the seller; only that a person is checking.
        "compliance": lifecycle.compliance_view(seller),
    }


def _seller(user) -> dict:
    seller = store.by_user(user.id)
    if not seller:
        raise HTTPException(409, "Apply to sell first.")
    return seller


def _active_seller(user) -> dict:
    seller = _seller(user)
    if seller["status"] == "SUSPENDED":
        raise HTTPException(403, "This seller account is suspended.")
    if seller["status"] in {"REJECTED", "CLOSED"}:
        raise HTTPException(403, "This seller account cannot sell.")
    if seller["status"] == "UNDER_REVIEW":
        raise HTTPException(409, "Your account is being reviewed.")
    if seller["status"] != "ACTIVE" or not seller["payout_verified"]:
        raise HTTPException(409, "Finish setting up your seller account first.")
    return seller


def _selling_seller(user) -> dict:
    seller = _active_seller(user)
    if seller["demo"]:
        raise HTTPException(409, "A demo seller takes part only in its own seller tour.")
    if not lifecycle.can_sell(seller):
        raise HTTPException(
            409, "Confirm your seller details (and tax id, if asked) to publish offers again."
        )
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
        "agent": row["agent"],
        "guidance": row["guidance"],
        "active": bool(row["active"]),
        "listing": bool(row["listing"]),
        "gtin": row["gtin"],
        "category": row["category"],
        "typical_price": str(row["typical_price"]) if row["typical_price"] is not None else None,
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
        "ai_max_round_drop_percent": settings.seller_ai_max_round_drop_percent,
        "negotiation_mode": settings.negotiation_mode,
        "payments": money.enabled(),
        "categories": catalog.CATEGORIES,
        "carriers": {k: v["label"] for k, v in tracking_numbers.CARRIERS.items()},
        "tracking_mode": settings.tracking_mode,
        "test_tracking_codes": tracking.TEST_CODES if settings.tracking_mode == "simulator" else {},
        "trusted_after": settings.payout_trusted_after_deliveries,
        "listing_limit": settings.listing_max_per_seller,
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
    seller = _seller(user)
    if seller["status"] in {"SUSPENDED", "REJECTED", "CLOSED"}:
        raise HTTPException(403, "This seller account cannot be activated.")
    used = accounts.consume_token(f"{user.id}:{body.code}", PURPOSE)
    if used is None or used[1] != seller["payout_email"]:
        raise HTTPException(400, "That code is wrong or expired.")
    store.update_seller(seller["id"], payout_verified=True, payout_verified_at=int(time.time()))
    audit.record(f"user:{user.id[:8]}", "seller.payout_verified", seller["code"])
    return _profile(lifecycle.evaluate(seller["id"]))


@router.post("/payout-email", status_code=202)
async def change_payout_email(body: PayoutEmail, user: FreshUser):
    """Where the money goes is the most sensitive field, so it needs a fresh identity check and a
    new code. Until the new address is confirmed the seller sits out of Blocs and is not paid."""
    seller = _seller(user)
    if seller["status"] in {"SUSPENDED", "REJECTED", "CLOSED"}:
        raise HTTPException(403, "This seller account is suspended.")
    if seller["demo"]:
        raise HTTPException(409, "A demo seller is paid to the sandbox account; it cannot change.")
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
    if not seller or seller["status"] in {"SUSPENDED", "REJECTED", "CLOSED"}:
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


# ---- identity check ----------------------------------------------------------------------------


@router.post("/identity/start")
async def start_identity(user: CurrentUser):
    seller = _seller(user)
    if seller["status"] in {"SUSPENDED", "REJECTED", "CLOSED"}:
        raise HTTPException(403, "This seller account cannot be verified.")
    if seller["identity_status"] == "verified":
        raise HTTPException(409, "Your identity is already verified.")
    if settings.verify_mode not in {"simulator", "stripe"}:
        raise HTTPException(409, "Identity checks are not switched on.")
    ratelimit.hit(f"seller-idv:{user.id}", 6, 3600)
    try:
        session_id, url = await identity.start(seller)
    except identity.IdentityError as exc:
        raise HTTPException(503, str(exc)) from None
    if settings.verify_mode == "stripe" and not url.startswith("https://verify.stripe.com/"):
        raise HTTPException(502, "The identity provider returned an unexpected address.")
    store.update_seller(seller["id"], identity_session=session_id, identity_status="pending")
    audit.record(f"seller:{seller['code']}", "seller.identity_started", seller["code"])
    return {"url": url, "simulated": settings.verify_mode == "simulator"}


@router.post("/identity/refresh")
async def refresh_identity(user: CurrentUser):
    """Re-read the check from the provider (useful when the seller returns before the webhook)."""
    seller = _seller(user)
    if not seller["identity_session"]:
        raise HTTPException(409, "Start the identity check first.")
    ratelimit.hit(f"seller-idv-refresh:{user.id}", 30, 3600)
    try:
        result = await identity.fetch(seller["identity_session"])
    except identity.IdentityError as exc:
        raise HTTPException(503, str(exc)) from None
    return _profile(lifecycle.apply_identity(seller, result))


@router.post("/identity/simulate")
async def simulate_identity(body: SimulatedCheck, user: CurrentUser):
    """The simulated provider's page. Only exists in VERIFY_MODE=simulator."""
    if settings.verify_mode != "simulator":
        raise HTTPException(404, "Not found.")
    seller = _seller(user)
    if body.session != seller["identity_session"]:
        raise HTTPException(404, "This check is not yours.")
    name = seller["legal_name"] if seller["business_type"] == "individual" else user.display_name
    try:
        identity.simulate_outcome(body.session, seller["id"], body.outcome == "verified", name)
        result = await identity.fetch(body.session)
    except identity.IdentityError as exc:
        raise HTTPException(409, str(exc)) from None
    return _profile(lifecycle.apply_identity(seller, result))


@hooks.post("/webhooks/identity", status_code=202)
async def identity_webhook(request: Request):
    ratelimit.hit(f"identity-hook:{client_ip(request)}", 300, 60)
    body = await request.body()
    if len(body) > 256 * 1024:
        raise HTTPException(413, "Too large.")
    if not identity.verify_webhook(request.headers.get("stripe-signature", ""), body):
        raise HTTPException(401, "Bad signature.")
    session_id = identity.session_from_webhook(body)
    seller = store.by_identity_session(session_id) if session_id else None
    if seller:
        try:
            # The provider is asked again; the webhook body is only a hint.
            lifecycle.apply_identity(seller, await identity.fetch(session_id))
        except identity.IdentityError:
            raise HTTPException(503, "Try again.") from None
    return {"received": True}


# ---- compliance (US INFORM Act and yearly certification) ----------------------------------------


@router.get("/compliance")
def compliance(user: CurrentUser):
    return lifecycle.compliance_view(_seller(user))


@router.post("/compliance")
def certify(body: Certify, user: FreshUser):
    seller = _active_seller(user)
    if not body.certify:
        raise HTTPException(422, "Confirm that your details are accurate and complete.")
    if seller["high_volume_since"] and not seller["tax_id_last4"] and not body.tax_id:
        raise HTTPException(422, "High-volume sellers must give a tax id.")
    ratelimit.hit(f"seller-certify:{user.id}", 10, 3600)
    return _profile(lifecycle.record_certification(seller, body.tax_id or None))


# ---- demand, offers and listings ---------------------------------------------------------------


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
        if bloc.origin == "demo_tour" or (bloc.closes_at and bloc.closes_at <= now):
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
            "origin": bloc.origin,
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
    seller = _selling_seller(user)
    if body.opening_price < body.floor:
        raise HTTPException(422, "Your opening price must be at or above your floor.")
    known = runtime.store.find_by_product(body.product_key)
    if known is None or known.origin == "demo_tour":
        raise HTTPException(404, "No Bloc exists for that product yet. Publish a listing instead.")
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
        body.agent,
        body.guidance,
    )
    audit.record(f"seller:{seller['code']}", "offer.saved", row["id"], known.title[:60])
    return _offer(row)


@router.post("/listings", status_code=201)
async def publish_listing(body: ListingIn, user: CurrentUser, runtime: RuntimeDep):
    """Publish a product before any buyer has asked for it. It opens a Bloc buyers can join."""
    seller = _selling_seller(user)
    if body.category not in catalog.CATEGORIES:
        raise HTTPException(422, "Choose a category from the list.")
    reason = catalog.prohibited(body.title)
    if reason:
        raise HTTPException(422, f"Maxx does not allow listings for {reason}.")
    gtin = None
    if body.gtin.strip():
        gtin = catalog.gtin14(body.gtin)
        if gtin is None:
            raise HTTPException(422, "That barcode number (GTIN, UPC or EAN) is not valid.")
    if not body.floor <= body.opening_price <= body.typical_price:
        raise HTTPException(
            422, "Use floor ≤ opening price ≤ typical price (buyers pay at most the typical price)."
        )
    key = catalog.product_key(body.title, gtin)
    existing = store.offers_for(seller["id"])
    if not any(o["product_key"] == key for o in existing) and (
        store.count_listings(seller["id"]) >= settings.listing_max_per_seller
    ):
        raise HTTPException(409, f"You can have {settings.listing_max_per_seller} live listings.")
    ratelimit.hit(f"seller-listing:{user.id}", 20, 3600)
    own = any(
        m.user_id == user.id and m.status == "HELD"
        for b in runtime.store.list_open()
        if b.product_key == key
        for m in b.members
    )
    if own:
        raise HTTPException(409, "You are a buyer in this product's Bloc; leave it to sell it.")
    bloc = next(
        (
            b
            for b in runtime.store.list_open()
            if b.product_key == key and (not b.closes_at or b.closes_at > int(time.time()))
        ),
        None,
    )
    if bloc is None:
        bloc = make_bloc(
            str(uuid.uuid4()),
            body.title,
            body.typical_price,
            mode=runtime.mode,
            personas=0,
            origin="listing",
        )
        # No comparable-price research for a seller's own listing: no market rows, no target.
        bloc.product_key = key
        bloc.market_mode = "unavailable"
        bloc.market_rows = []
        bloc.target_price = None
        runtime.store.create(bloc)
    row = store.upsert_offer(
        seller["id"],
        key,
        bloc.title,
        body.stock,
        body.floor,
        body.opening_price,
        body.strategy,
        body.agent,
        body.guidance,
        listing={"gtin": gtin, "category": body.category, "typical_price": body.typical_price},
    )
    audit.record(f"seller:{seller['code']}", "listing.published", row["id"], body.title[:60])
    return {**_offer(row), "bloc_id": bloc.id}


@router.get("/listings")
def my_listings(user: CurrentUser, runtime: RuntimeDep):
    seller = _active_seller(user)
    out = []
    for offer in store.offers_for(seller["id"]):
        if not offer["listing"]:
            continue
        bloc = next(
            (b for b in runtime.store.list_open() if b.product_key == offer["product_key"]), None
        )
        out.append(
            {
                **_offer(offer),
                "bloc_id": bloc.id if bloc else None,
                "buyers": _demand(bloc)["buyers"] if bloc else 0,
                "closes_at": bloc.closes_at if bloc else None,
            }
        )
    return out


@router.post("/offers/{offer_id}/active")
def toggle_offer(offer_id: str, body: Active, user: CurrentUser):
    seller = _selling_seller(user) if body.active else _active_seller(user)
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
    with storage.get_store().engine.connect() as db:
        return [
            dict(r._mapping)
            for r in db.execute(select(schema.payouts).where(schema.payouts.c.seller_id == code))
        ]


# ---- orders to ship ------------------------------------------------------------------------------

GATE_TEXT = {
    "under_review": "On hold while Maxx reviews a delivery problem.",
    "awaiting_carrier": "Paid once the carrier scans the parcel.",
    "awaiting_delivery": "Paid once the parcel is delivered.",
}


def _order_for_seller(order: dict, seller: dict, with_address: bool) -> dict:
    case = orders.open_case_for(order["id"])
    fee = (Decimal(order["amount"]) * Decimal(settings.platform_fee_percent) / 100).quantize(
        Decimal("0.01")
    )
    payout = fulfilment._payout_for_order(order["id"])
    gate = (
        fulfilment.payout_gate(order, seller)
        if order["status"] in {"SHIPPED", "DELIVERED"} and not payout
        else None
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
        "tracking_status": order["tracking_status"],
        "tracking_events": fulfilment.tracking_history(order["id"]),
        "estimated_delivery": order["estimated_delivery"],
        "review_flag": order["review_flag"] if fulfilment.flagged(order) else "",
        "created_at": order["created_at"],
        "case_id": case["id"] if case else None,
        "payout": {
            "status": payout["status"],
            "item_status": payout["item_status"],
            "net": str(payout["net_amount"]),
            "failure_reason": payout["failure_reason"],
            "simulated": bool(payout["simulated"]),
        }
        if payout
        else None,
        "payout_waiting": GATE_TEXT.get(gate) if gate else None,
        "demo_buyer": order["buyer_id"].startswith("demo-buyer-"),
        "address": None,
    }
    if with_address and order["status"] in {"AWAITING_SHIPMENT", "SHIPPED"}:
        view["address"] = orders.read_blob(order["address_blob"])
    return view


@router.get("/orders")
def seller_orders(user: CurrentUser):
    seller = _seller(user)
    return [
        _order_for_seller(o, seller, True)
        for o in orders.orders_where(seller_user_id=user.id)
        if o["seller_code"] == seller["code"]
    ]


@router.post("/orders/{order_id}/ship")
async def ship_order(order_id: str, body: Ship, user: CurrentUser):
    seller = _seller(user)
    if seller["status"] in {"REJECTED", "CLOSED"}:
        raise HTTPException(403, "This seller account cannot ship orders.")
    ratelimit.hit(f"seller-ship:{user.id}", 120, 3600)
    try:
        order = await fulfilment.ship(user.id, order_id, body.carrier.strip(), body.tracking)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except fulfilment.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return _order_for_seller(order, seller, True)


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
    _seller(user)
    mine = orders.orders_where(seller_user_id=user.id)
    by_id = {o["id"]: o for o in mine}
    return [_case_view(c, by_id[c["order_id"]]) for c in orders.cases_for_orders(list(by_id))]


@router.post("/cases/{case_id}/reply")
def reply_case(case_id: str, body: Reply, user: CurrentUser):
    # Even a suspended seller must be able to answer for orders they already have.
    _seller(user)
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
    seller = _seller(user)
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
