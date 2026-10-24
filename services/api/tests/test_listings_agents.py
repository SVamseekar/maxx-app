"""Seller listings, AI seller agents and their hard limits, and the judge's seller tour."""

import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.demo import tour
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.main import app
from maxx.money import ledger
from maxx.money import service as money
from maxx.negotiate.adapters import Bid, FixtureAdapter, guard_ai_bid, rules_bid
from maxx.negotiate.contracts import Seller
from maxx.negotiate.runner import run_negotiation
from maxx.sellers import catalog
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.marketplace import buy, onboard, wait_settled
from tests.test_fulfilment import runtime as runtime  # noqa: F401 - shared fixture

LISTING = {
    "title": "Northwind Studio Monitor Headphones · Black",
    "gtin": "4006381333931",
    "category": "audio",
    "typical_price": "180.00",
    "stock": 5,
    "floor": "120.00",
    "opening_price": "170.00",
    "strategy": "balanced",
    "agent": "ai",
    "guidance": "Sell all five this month.\x07",
}


def test_gtins_are_checked_and_titles_screened():
    assert catalog.gtin14("4006381333931") == "04006381333931"
    assert catalog.gtin14("036000291452") == "00036000291452"  # a UPC is the same product
    assert catalog.gtin14("4006381333932") is None
    assert catalog.gtin14("12AB") is None
    assert catalog.prohibited("Replica designer watch") == "counterfeit goods"
    assert catalog.prohibited("Refurbished laptop") == "used goods"
    assert catalog.prohibited("Northwind Studio Monitor Headphones") is None


def test_a_seller_can_list_a_product_nobody_has_asked_for_yet(runtime):  # noqa: F811
    with TestClient(app) as seller, TestClient(app) as buyer:
        sign_up(seller, "seller@example.com", "Sam Seller")
        onboard(seller)
        made = seller.post("/seller/listings", json=LISTING)
        assert made.status_code == 201, made.text
        listing = made.json()
        assert (
            listing["listing"] and listing["agent"] == "ai" and listing["gtin"] == "04006381333931"
        )
        assert "\x07" not in listing["guidance"]
        bloc = runtime.store.get(listing["bloc_id"])
        assert bloc.origin == "listing" and bloc.sellers == []  # no simulated sellers
        assert bloc.product_key == "gtin:04006381333931" and bloc.market_rows == []
        # Publishing the same barcode again updates the listing, it does not open a second Bloc.
        again = seller.post("/seller/listings", json={**LISTING, "title": "Same thing, longer"})
        assert again.json()["bloc_id"] == listing["bloc_id"]
        assert seller.get("/seller/listings").json()[0]["buyers"] == 0
        # A buyer joins and wins from the seller's AI agent; the order is the seller's to ship.
        sign_up(buyer, "buyer@example.com", "Bea Buyer")
        hold = buy(buyer, listing["bloc_id"], "175")
        assert buyer.post(f"/blocs/{listing['bloc_id']}/start").status_code == 202
        books = wait_settled(buyer, listing["bloc_id"])
        assert books["captured_count"] == 1
        order = orders.order_for_payment(ledger.by_order(hold)["id"])
        assert order["seller_code"] == listing_code(seller) and not order["simulated"]
        events = runtime.store.get(listing["bloc_id"]).events
        offers = [e.data["price"] for e in events if e.type == "seller_offer"]
        assert offers and all(Decimal(p) >= Decimal("120.00") for p in offers)


def listing_code(client) -> str:
    return client.get("/seller").json()["seller"]["code"]


def test_listings_that_break_the_rules_are_refused(runtime):  # noqa: F811
    with TestClient(app) as seller:
        sign_up(seller, "seller@example.com")
        onboard(seller)
        assert (
            seller.post(
                "/seller/listings", json={**LISTING, "title": "Replica studio headphones"}
            ).status_code
            == 422
        )
        assert (
            seller.post("/seller/listings", json={**LISTING, "gtin": "4006381333932"}).status_code
            == 422
        )
        assert (
            seller.post("/seller/listings", json={**LISTING, "category": "weapons"}).status_code
            == 422
        )
        assert (
            seller.post("/seller/listings", json={**LISTING, "floor": "175.00"}).status_code == 422
        )
        assert (
            seller.post("/seller/listings", json={**LISTING, "agent": "magic"}).status_code == 422
        )
        assert seller.post("/seller/listings", json={**LISTING, "extra": 1}).status_code == 422


def test_an_administrator_takedown_releases_every_buyer(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    with TestClient(app) as seller, TestClient(app) as buyer, TestClient(app) as boss:
        sign_up(seller, "seller@example.com")
        onboard(seller)
        listing = seller.post("/seller/listings", json=LISTING).json()
        sign_up(buyer, "buyer@example.com")
        hold = buy(buyer, listing["bloc_id"], "175")
        sign_up(boss, "boss@example.com", "Boss")
        assert (
            boss.post(
                f"/admin/listings/{listing['id']}/takedown", json={"note": "Brand complaint"}
            ).status_code
            == 200
        )
        bloc = runtime.store.get(listing["bloc_id"])
        assert bloc.status == "FAILED"
        asyncio.run(money.settle_bloc(runtime.store, listing["bloc_id"]))
        wait_settled(buyer, listing["bloc_id"])
        assert ledger.by_order(hold)["status"] == "VOIDED"
        assert "seller.listing" in {n["kind"] for n in seller.get("/notifications").json()["items"]}


def seller(**changes) -> Seller:
    base = {"id": "S1", "floor": "100", "opening_price": "150", "stock": 4, "account_id": "u"}
    return Seller(**{**base, **changes})


def test_an_ai_agent_can_never_break_its_sellers_limits():
    s = seller(agent="ai")
    offer, applied = guard_ai_bid(s, Bid(price="50", max_qty=99), Decimal("140"))
    assert offer.price == Decimal("117.50") and offer.max_qty == 4  # at most 15% of 150 per round
    assert set(applied) == {"max_drop", "stock"}
    offer, applied = guard_ai_bid(s, Bid(price="149", max_qty=1), Decimal("120"))
    assert offer.price == Decimal("120.00") and applied == ["no_increase"]
    offer, applied = guard_ai_bid(s, Bid(price="90", max_qty=1), Decimal("101"))
    assert offer.price == Decimal("100.00") and applied == ["floor"]
    offer, applied = guard_ai_bid(s, Bid(price="999", max_qty=1), None)
    assert offer.price == Decimal("150.00") and applied == ["opening"]
    assert guard_ai_bid(s, Bid(price="120", max_qty=1, withdraw=True), None) == (None, [])


def test_a_rules_seller_never_has_a_model_bid_for_it(runtime):  # noqa: F811
    class Watching(FixtureAdapter):
        def __init__(self):
            super().__init__()
            self.asked = []

        async def seller(self, context):
            self.asked.append(context["seller_id"])
            return await super().seller(context)

    bloc = runtime.store.get("demo-success")
    bloc.sellers.append(seller(id="SREAL1", concession=Decimal("0.05")))
    runtime.store.save(bloc)
    from maxx.negotiate.blocs import transition

    transition(bloc, "NEGOTIATING")
    runtime.store.save(bloc)
    adapter = Watching()
    asyncio.run(run_negotiation(runtime.store, "demo-success", adapter, round_delay=0))
    assert "SREAL1" not in adapter.asked and "A" in adapter.asked
    prices = [
        Decimal(e.data["price"])
        for e in runtime.store.get("demo-success").events
        if e.type == "seller_offer" and e.data["seller"] == "SREAL1"
    ]
    assert prices[0] == rules_bid(seller(concession=Decimal("0.05")), 1).price


@pytest.fixture
def tour_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "tracking_mode", "simulator")
    monkeypatch.setattr(settings, "simulated_seller_ship_seconds", 0)


def test_the_seller_tour_shows_a_judge_the_whole_seller_side(runtime, tour_on):  # noqa: F811
    with TestClient(app) as judge:
        sign_up(judge, "judge@example.com", "Jude")
        assert judge.get("/demo/seller-tour").json() == {"available": True}
        started = judge.post("/demo/seller-tour")
        assert started.status_code == 201, started.text
        bloc_id = started.json()["bloc_id"]
        wait_settled(judge, bloc_id)
        profile = judge.get("/seller").json()["seller"]
        assert profile["demo"] and profile["status"] == "ACTIVE"
        mine = judge.get("/seller/orders").json()
        assert len(mine) == 3 and all(o["demo_buyer"] for o in mine)
        assert tour.act_for_demo_buyers() == 3
        ready = judge.get("/seller/orders").json()
        assert all(o["status"] == "AWAITING_SHIPMENT" and o["address"] for o in ready)
        shipped = judge.post(
            f"/seller/orders/{ready[0]['id']}/ship",
            json={"carrier": "ups", "tracking": "EZ4000000004"},  # simulator: delivered
        )
        assert shipped.status_code == 200, shipped.text
        asyncio.run(fulfilment.sweep())
        order = orders.get_order(ready[0]["id"])
        assert order["status"] == "DELIVERED"
        paid = judge.get("/seller/orders").json()
        done = next(o for o in paid if o["id"] == ready[0]["id"])
        assert done["payout"]["status"] == "SENT" and done["payout"]["simulated"]
        demo = sellers.by_code(profile["code"])
        assert demo["payout_email"] == settings.paypal_seller_receiver
        # Demo buyers are not accounts and never get mail.
        delivered = orders.orders_in(["DELIVERED"])
        assert all(o["buyer_id"].startswith("demo-buyer-") for o in delivered)
        # Postgres enforces the 36-character user id columns that SQLite ignores.
        assert all(len(o["buyer_id"]) <= 36 for o in delivered)


def test_the_tour_is_refused_outside_the_demo_setup(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(settings, "paypal_client_id", "id")
    monkeypatch.setattr(settings, "paypal_client_secret", "secret")
    assert not tour.enabled()
    with TestClient(app) as judge:
        sign_up(judge, "judge@example.com")
        assert judge.post("/demo/seller-tour").status_code == 404
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    monkeypatch.setattr(settings, "demo_tools", False)
    assert not tour.enabled()


def test_a_real_seller_cannot_be_turned_into_a_demo_seller(runtime, tour_on):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com")
        onboard(client)
        refused = client.post("/demo/seller-tour")
        assert refused.status_code == 409 and "real seller" in refused.json()["detail"]


def test_a_tour_bloc_is_private_and_closed_to_real_buyers(runtime, tour_on):  # noqa: F811
    with TestClient(app) as judge, TestClient(app) as buyer:
        sign_up(judge, "judge@example.com", "Jude")
        sign_up(buyer, "buyer@example.com", "Bea")
        # Hold the negotiation back so the Bloc is still open when the buyer tries.
        start = runtime.start
        runtime.start = lambda bloc_id, starter="": asyncio.sleep(0)
        try:
            bloc_id = judge.post("/demo/seller-tour").json()["bloc_id"]
        finally:
            runtime.start = start
        assert bloc_id not in {b["id"] for b in buyer.get("/blocs").json()}
        assert buyer.get(f"/blocs/{bloc_id}").status_code == 200  # the link still works
        refused = buyer.post(f"/money/blocs/{bloc_id}/hold", json={"max_price": "120"})
        assert refused.status_code == 409 and "seller tour" in refused.json()["detail"]


def test_a_tour_that_fails_to_start_is_ended_and_its_offer_paused(
    runtime,  # noqa: F811
    tour_on,
    monkeypatch,
):
    real = money.authorize_hold
    calls = []

    async def flaky(store, buyer, order_id):
        calls.append(order_id)
        if len(calls) == 2:
            raise RuntimeError("provider went away")
        return await real(store, buyer, order_id)

    monkeypatch.setattr(money, "authorize_hold", flaky)
    with TestClient(app, raise_server_exceptions=False) as judge:
        sign_up(judge, "judge@example.com", "Jude")
        assert judge.post("/demo/seller-tour").status_code == 500
        seller = sellers.by_user(judge.get("/auth/me").json()["user"]["id"])
        offers = sellers.offers_for(seller["id"])
        assert len(offers) == 1 and not offers[0]["active"]
        bloc = next(b for b in runtime.store.list() if b.product_key == offers[0]["product_key"])
        assert bloc.status == "FAILED"
        assert all(m.status != "HELD" for m in bloc.members)


def test_demo_and_real_sellers_never_cross(runtime, tour_on):  # noqa: F811
    with TestClient(app) as judge, TestClient(app) as seller:
        sign_up(judge, "judge@example.com", "Jude")
        sign_up(seller, "seller@example.com", "Sam")
        onboard(seller)
        start = runtime.start
        runtime.start = lambda bloc_id, starter="": asyncio.sleep(0)
        try:
            bloc_id = judge.post("/demo/seller-tour").json()["bloc_id"]
        finally:
            runtime.start = start
        tour_bloc = runtime.store.get(bloc_id)
        assert bloc_id not in {o["bloc_id"] for o in seller.get("/seller/opportunities").json()}
        offer = {
            "product_key": tour_bloc.product_key,
            "stock": 2,
            "floor": "60",
            "opening_price": "90",
            "strategy": "balanced",
        }
        assert seller.post("/seller/offers", json=offer).status_code == 404
        # The demo seller cannot sell outside its tour.
        refused = judge.post("/seller/offers", json={**offer, "product_key": "demo-success"})
        assert refused.status_code == 409 and "tour" in refused.json()["detail"]
        real = runtime.store.get("demo-success")
        demo = sellers.by_user(judge.get("/auth/me").json()["user"]["id"])
        sellers.upsert_offer(
            demo["id"], real.product_key, real.title, 2, Decimal("1"), Decimal("2"), "balanced"
        )
        sellers.attach(real)
        assert demo["code"] not in {s.id for s in real.sellers}


def test_the_room_never_learns_which_limit_an_ai_agent_hit(runtime):  # noqa: F811
    class Greedy(FixtureAdapter):
        async def seller(self, context):
            if context["seller_id"] == "SAI1":
                return {"price": "1", "max_qty": 999}  # far below the floor, beyond stock
            return await super().seller(context)

    from maxx import audit
    from maxx.negotiate.blocs import transition

    bloc = runtime.store.get("demo-success")
    bloc.sellers.append(seller(id="SAI1", agent="ai", floor="100", opening_price="150"))
    transition(bloc, "NEGOTIATING")
    runtime.store.save(bloc)
    asyncio.run(run_negotiation(runtime.store, "demo-success", Greedy(), round_delay=0))
    events = runtime.store.get("demo-success").events
    ai_offers = [e for e in events if e.type == "seller_offer" and e.data["seller"] == "SAI1"]
    assert ai_offers and all(e.data["clamped"] for e in ai_offers)
    # The room sees only "clamped"; which limit (here the floor and stock) stays in the audit log.
    assert not any(e.type == "agent_limited" or "limits" in e.data for e in events)
    limited = audit.recent(50, "agent.limited")
    assert limited and "floor" in limited[0]["detail"] and "stock" in limited[0]["detail"]
