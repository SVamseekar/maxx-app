"""The judge's seller tour: see the seller side end to end in a few minutes.

It gives the signed-in person a demo seller account (every onboarding step marked done, clearly
labelled DEMO, paid only to the PayPal sandbox receiver), publishes an AI-agent offer for a demo
product, and fills a Bloc with three demo buyers who place simulator holds. The negotiation then
runs; the demo seller wins orders, the demo buyers give addresses automatically, and the person
ships with a test tracking number and watches the carrier updates and the payout arrive.

It only runs with PAYPAL_MODE=simulator and DEMO_TOOLS on. Demo buyers are ids, not accounts:
nobody can sign in as one, and no email is ever sent to them.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

from maxx import audit
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.money import service as money
from maxx.money.simulator import get_simulator
from maxx.negotiate.blocs import make_bloc
from maxx.sellers import rules, store

PRODUCT = "Aurora ANC wireless earbuds · Graphite (demo seller tour)"
TYPICAL = Decimal("120.00")
BUYER_MAXIMUMS = [Decimal("115.00"), Decimal("112.00"), Decimal("110.00")]
DEMO_ADDRESSES = [
    ("Ada Demo", "1 Sample Street", "Springfield", "62701", "US"),
    ("Ben Demo", "22 Example Avenue", "Portland", "97201", "US"),
    ("Cy Demo", "300 Test Road", "Austin", "73301", "US"),
]


class TourError(ValueError):
    """Safe to show the person."""


def enabled() -> bool:
    on = (
        settings.demo_tools
        if settings.demo_tools is not None
        else settings.environment != "production"
    )
    return bool(on) and settings.paypal_mode == "simulator"


def ensure_demo_seller(user) -> dict:
    seller = store.by_user(user.id)
    if seller and not seller["demo"]:
        raise TourError("You already have a real seller account; the tour uses a demo one.")
    if seller:
        return seller
    now = int(time.time())
    profile = {
        "business_name": f"{user.display_name[:40]}'s demo shop",
        "legal_name": f"{user.display_name[:60]} (demo)",
        "business_type": "individual",
        "country": "US",
        "address_line1": "Demo only, not a real address",
        "address_city": "Demo",
        "address_region": "",
        "address_postal": "00000",
        "phone": "+1 555 0100",
        "support_email": user.email,
        "website": "",
        "trade_register_no": "",
        "payout_email": settings.paypal_seller_receiver,
        "ship_within_days": 2,
        "ships_to": "US,CA,GB",
        "return_days": 30,
        "return_policy": "Demo seller: return any item within 30 days for a full refund.",
        "terms_version": rules.TERMS_VERSION,
    }
    seller = store.create(user.id, profile)
    store.update_seller(
        seller["id"],
        payout_verified=True,
        payout_verified_at=now,
        identity_status="verified",
        identity_name=user.display_name[:160],
        identity_country="US",
        identity_checked_at=now,
        screening_status="clear",
        screened_at=now,
        reviewed_at=now,
        reviewed_by="demo-tour",
        recertify_by=now + 365 * 86400,
        status="ACTIVE",
        demo=True,
    )
    audit.record(f"user:{user.id[:8]}", "demo.seller_created", seller["code"])
    return store.by_id(seller["id"])


async def start(runtime, user) -> dict:
    if not enabled():
        raise TourError("The seller tour runs only in the demo (PayPal simulator) setup.")
    seller = ensure_demo_seller(user)
    bloc_id = str(uuid.uuid4())
    bloc = make_bloc(bloc_id, PRODUCT, TYPICAL, mode=runtime.mode, personas=2, origin="demo_tour")
    bloc.product_key = f"demo-tour:{seller['code']}:{bloc_id[:8]}"
    bloc.market_rows, bloc.market_mode, bloc.target_price = [], "unavailable", None
    for persona in bloc.sellers:
        # Two simulated competitors who will not go below $104, so the demo seller can win.
        persona.floor, persona.opening_price, persona.stock = (
            Decimal("104.00"),
            Decimal("118.00"),
            1,
        )
    runtime.store.create(bloc)
    offer = store.upsert_offer(
        seller["id"],
        bloc.product_key,
        PRODUCT,
        3,
        Decimal("72.00"),
        Decimal("108.00"),
        "balanced",
        "ai",
        "I would rather sell all three units this week than hold out for a higher price.",
    )
    try:
        simulator = get_simulator()
        for maximum in BUYER_MAXIMUMS:
            buyer = f"demo-buyer-{uuid.uuid4().hex[:25]}"  # fits the 36-character user id columns
            current = runtime.store.get(bloc_id)
            payment = await money.start_hold(current, buyer, maximum)
            simulator.approve(payment["order_id"])
            await money.authorize_hold(runtime.store, buyer, payment["order_id"])
        await runtime.start(bloc_id, starter=user.id)
    except Exception:
        # Never leave a half-built demo open: end it so the settlement worker releases any hold.
        await _abandon(runtime, bloc_id, seller["id"], offer["id"])
        raise
    audit.record(f"seller:{seller['code']}", "demo.tour_started", bloc_id)
    return {"bloc_id": bloc_id, "seller_code": seller["code"]}


async def _abandon(runtime, bloc_id: str, seller_id: str, offer_id: str) -> None:
    from maxx.negotiate.runner import terminal_failure

    store.set_active(seller_id, offer_id, False)
    async with runtime.lock:
        bloc = runtime.store.get(bloc_id)
        if bloc.status in {"FORMING", "OPEN"}:
            terminal_failure(bloc, "The seller tour could not start.")
            runtime.store.save(bloc)


def act_for_demo_buyers() -> int:
    """Demo buyers give a delivery address as soon as they win, like an attentive buyer."""
    acted = 0
    for order in orders.orders_in(["AWAITING_ADDRESS"]):
        if not order["buyer_id"].startswith("demo-buyer-"):
            continue
        name, line1, city, postal, country = DEMO_ADDRESSES[acted % len(DEMO_ADDRESSES)]
        address = orders.add_address(
            order["buyer_id"],
            orders.Address(
                label="Demo", name=name, line1=line1, city=city, postal=postal, country=country
            ),
        )
        try:
            fulfilment.set_address(order["buyer_id"], order["id"], address["id"])
            acted += 1
        except (LookupError, fulfilment.Refused):
            continue
    return acted
