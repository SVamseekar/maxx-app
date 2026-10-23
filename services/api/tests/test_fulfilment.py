"""Fulfilment: addresses, shipping, pay-on-ship, refunds, disputes. Maxx enforces, never ships."""

import asyncio
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from maxx import schema, storage
from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.main import app
from maxx.money import ledger
from maxx.money import service as money
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.marketplace import ADDRESS, buy, offer, onboard, wait_settled


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


class Market:
    """A real seller who undercuts every simulated one, and a real buyer who wins from them."""

    def __init__(self, runtime, bloc="demo-success", buyer_email="buyer@example.com"):
        self.runtime, self.bloc = runtime, bloc
        self.seller, self.buyer = TestClient(app), TestClient(app)
        self.seller.__enter__(), self.buyer.__enter__()
        self.user = sign_up(self.seller, "seller@example.com", "Sam Seller")
        self.profile = onboard(self.seller)
        self.code = self.profile["code"]
        offer(self.seller, floor="100.00", opening_price="100.00", stock=100000)
        self.buyer_user = sign_up(self.buyer, buyer_email, "Bea Buyer")

    def run(self, bloc=None, buyer=None):
        buyer = buyer or self.buyer
        bloc = bloc or self.bloc
        self.hold_id = buy(buyer, bloc)
        assert buyer.post(f"/blocs/{bloc}/start").status_code == 202
        wait_settled(buyer, bloc)
        payment = ledger.by_order(self.hold_id)
        self.order = orders.order_for_payment(payment["id"])
        return self.order

    def address(self, buyer=None, **changes):
        buyer = buyer or self.buyer
        made = buyer.post("/addresses", json={**ADDRESS, **changes})
        assert made.status_code == 201, made.text
        return made.json()["id"]

    def close(self):
        self.seller.__exit__(None, None, None)
        self.buyer.__exit__(None, None, None)


@pytest.fixture
def market(runtime):
    m = Market(runtime)
    yield m
    m.close()


def ship(m, order_id=None, tracking="1Z999AA10123456784"):
    return m.seller.post(
        f"/seller/orders/{order_id or m.order['id']}/ship",
        json={"carrier": "UPS", "tracking": tracking},
    )


def payout_for(order_id):
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.payouts).where(schema.payouts.c.order_id == order_id)
        ).first()
    return dict(row._mapping) if row else None


def test_winning_from_a_real_seller_creates_an_order_and_holds_the_money(market):
    order = market.run()
    assert order["status"] == "AWAITING_ADDRESS" and order["seller_code"] == market.code
    assert order["amount"] == Decimal("100.00")
    assert payout_for(order["id"]) is None  # the seller is not paid yet
    books = market.buyer.get("/money/blocs/demo-success/ledger").json()
    assert books["held_for_shipping"] == "100.00" and books["reconciled"] is True
    assert Decimal(books["seller_payouts"]) == 0


def test_the_seller_cannot_ship_before_there_is_an_address_and_never_sees_buyer_contact(market):
    market.run()
    seller_view = market.seller.get("/seller/orders").json()[0]
    assert seller_view["address"] is None and seller_view["status"] == "AWAITING_ADDRESS"
    refused = ship(market)
    assert refused.status_code == 409 and "address" in refused.json()["detail"]
    assert "buyer@example.com" not in str(seller_view)


def test_address_then_shipment_pays_the_seller_once_with_the_fee_taken(market):
    market.run()
    address_id = market.address()
    chosen = market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": address_id}
    )
    assert chosen.status_code == 200 and chosen.json()["status"] == "AWAITING_SHIPMENT"
    seen = market.seller.get("/seller/orders").json()[0]
    assert seen["address"]["name"] == "Bea Buyer" and seen["address"]["city"] == "Leeds"
    assert seen["your_share"] == "95.00"
    shipped = ship(market)
    assert shipped.status_code == 200 and shipped.json()["status"] == "SHIPPED"
    payout = payout_for(market.order["id"])
    assert payout["status"] == "SENT" and Decimal(payout["net_amount"]) == Decimal("95.00")
    assert payout["receiver"] == "pay@shop.example" and payout["simulated"]
    assert ship(market).status_code == 409  # cannot be shipped twice, so cannot be paid twice
    books = market.buyer.get("/money/blocs/demo-success/ledger").json()
    assert books["reconciled"] is True and books["held_for_shipping"] == "0.00"
    assert Decimal(books["seller_payouts"]) == Decimal("95.00")
    view = market.buyer.get("/orders").json()[0]
    assert view["tracking"] == "1Z999AA10123456784" and view["has_address"] is True
    assert "Market Road" not in str(view)  # addresses never come back to lists


def test_a_seller_who_does_not_ship_to_that_country_is_refused(market):
    market.run()
    france = market.address(country="FR", postal="75001", city="Paris")
    refused = market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": france}
    )
    assert refused.status_code == 409 and "does not ship" in refused.json()["detail"]


def test_only_the_selling_account_can_ship_and_only_the_buyer_can_change_the_address(
    runtime, market
):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    with TestClient(app) as stranger:
        sign_up(stranger, "stranger@example.com")
        onboard(stranger, "other@shop.example")
        assert (
            stranger.post(
                f"/seller/orders/{market.order['id']}/ship",
                json={"carrier": "UPS", "tracking": "ABC123456"},
            ).status_code
            == 404
        )
        assert (
            stranger.post(
                f"/orders/{market.order['id']}/address", json={"address_id": "x" * 10}
            ).status_code
            == 404
        )
        assert stranger.get(f"/orders/{market.order['id']}").status_code == 404
    bad = market.seller.post(
        f"/seller/orders/{market.order['id']}/ship", json={"carrier": "UPS", "tracking": "!!"}
    )
    assert bad.status_code == 422


def test_buyer_can_cancel_before_shipping_and_gets_a_full_refund(market):
    market.run()
    cancelled = market.buyer.post(f"/orders/{market.order['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    payment = ledger.by_order(market.hold_id)
    assert payment["status"] == "REFUNDED"
    assert ship(market).status_code == 409 and payout_for(market.order["id"]) is None
    books = market.buyer.get("/money/blocs/demo-success/ledger").json()
    assert books["refunded_total"] == "100.00" and Decimal(books["seller_payouts"]) == 0
    assert market.buyer.post(f"/orders/{market.order['id']}/cancel").status_code == 409


def test_no_address_in_time_cancels_and_refunds(market):
    market.run()
    orders.update_order(market.order["id"], None, ship_by=int(time.time()) - 5)
    done = asyncio.run(fulfilment.sweep())
    assert done["refunded"] == 1
    assert orders.get_order(market.order["id"])["status"] == "CANCELLED"
    assert ledger.by_order(market.hold_id)["status"] == "REFUNDED"


def test_not_shipping_in_time_refunds_the_buyer_and_costs_the_seller_a_strike(market):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    late = int(time.time()) - (settings.ship_grace_days + 1) * 86400
    orders.update_order(market.order["id"], None, ship_by=late)
    asyncio.run(fulfilment.sweep())
    assert orders.get_order(market.order["id"])["status"] == "CANCELLED"
    assert ledger.by_order(market.hold_id)["status"] == "REFUNDED"
    assert sellers.by_code(market.code)["strikes"] == 1
    assert payout_for(market.order["id"]) is None


def test_three_strikes_suspend_the_seller(market):
    seller = sellers.by_code(market.code)
    for _ in range(3):
        fulfilment._strike(market.code, "test")
    assert sellers.by_code(market.code)["status"] == "SUSPENDED"
    assert sellers.attach(market.runtime.store.get("demo-success").model_copy(deep=True)) == 0
    assert seller["status"] == "ACTIVE"


def test_a_problem_after_shipping_pauses_nothing_already_paid_but_a_refund_is_recovered(market):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    short = market.buyer.post(
        f"/orders/{market.order['id']}/problem", json={"kind": "not_received", "message": "short"}
    )
    assert short.status_code == 422
    opened = market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "not_received", "message": "The parcel never arrived after three weeks."},
    )
    assert opened.status_code == 201
    case_id = opened.json()["case_id"]
    again = market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "other", "message": "Second problem for the same order."},
    )
    assert again.status_code == 409  # one open problem per order
    seller_cases = market.seller.get("/seller/cases").json()
    assert seller_cases[0]["id"] == case_id and seller_cases[0]["messages"][0]["actor"] == "buyer"
    assert (
        market.seller.post(f"/seller/cases/{case_id}/reply", json={"body": "Checking."}).status_code
        == 200
    )
    agreed = market.seller.post(f"/seller/cases/{case_id}/refund")
    assert agreed.status_code == 200 and agreed.json()["status"] == "RESOLVED_REFUNDED"
    assert ledger.by_order(market.hold_id)["status"] == "REFUNDED"
    assert orders.get_order(market.order["id"])["status"] == "REFUNDED"
    assert orders.owed_by(market.code) == Decimal("95.00")  # paid out earlier, so owed back


def test_what_a_seller_owes_is_taken_from_the_next_payout(market, runtime):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    case = market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "not_as_described", "message": "It is a different model from the listing."},
    ).json()["case_id"]
    market.seller.post(f"/seller/cases/{case}/refund")
    assert orders.owed_by(market.code) == Decimal("95.00")
    # A second sale from another Bloc: its payout first repays the debt.
    with TestClient(app) as second:
        sign_up(second, "buyer2@example.com", "Cy Buyer")
        order2 = market.run("demo-flaky", second)
        second.post(f"/orders/{order2['id']}/address", json={"address_id": market.address(second)})
        assert ship(market, order2["id"], "TRACK00002").status_code == 200
    payout = payout_for(order2["id"])
    assert payout["status"] == "OFFSET" and Decimal(payout["net_amount"]) == 0
    assert orders.owed_by(market.code) == Decimal("0.00")


def test_a_seller_who_ignores_a_problem_loses_it(market):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    case = market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "not_received", "message": "Nothing has come, no tracking updates."},
    ).json()["case_id"]
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.cases)
            .where(schema.cases.c.id == case)
            .values(respond_by=int(time.time()) - 5)
        )
    done = asyncio.run(fulfilment.sweep())
    assert done["case_refunds"] == 1
    assert ledger.by_order(market.hold_id)["status"] == "REFUNDED"
    assert orders.get_case(case)["status"] == "RESOLVED_REFUNDED"
    assert sellers.by_code(market.code)["strikes"] == 1


def test_a_seller_reply_stops_the_automatic_refund_and_a_buyer_can_withdraw(market):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    case = market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "other", "message": "Please confirm the delivery date for me."},
    ).json()["case_id"]
    market.seller.post(f"/seller/cases/{case}/reply", json={"body": "It arrives Tuesday."})
    with storage.get_store().engine.begin() as db:
        db.execute(
            update(schema.cases)
            .where(schema.cases.c.id == case)
            .values(respond_by=int(time.time()) - 5)
        )
    assert asyncio.run(fulfilment.sweep())["case_refunds"] == 0
    assert market.buyer.post(f"/cases/{case}/withdraw").status_code == 200
    assert orders.get_case(case)["status"] == "WITHDRAWN"
    assert market.buyer.post(f"/cases/{case}/message", json={"body": "Thanks"}).status_code == 409


def test_delivery_is_confirmed_by_the_buyer_or_automatically(market):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    assert (
        market.buyer.post(f"/orders/{market.order['id']}/delivered").json()["status"] == "DELIVERED"
    )
    assert market.buyer.post(f"/orders/{market.order['id']}/delivered").status_code == 409


def test_unconfirmed_orders_complete_on_their_own_and_addresses_are_purged(market, monkeypatch):
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    old = int(time.time()) - (settings.delivery_auto_confirm_days + 1) * 86400
    orders.update_order(market.order["id"], None, shipped_at=old)
    assert asyncio.run(fulfilment.sweep())["delivered"] == 1
    assert orders.get_order(market.order["id"])["address_blob"] is not None
    ancient = int(time.time()) - (settings.address_retention_days + 1) * 86400
    orders.update_order(market.order["id"], None, delivered_at=ancient)
    assert asyncio.run(fulfilment.sweep())["purged"] == 1
    assert orders.get_order(market.order["id"])["address_blob"] is None


def test_a_new_payout_address_waits_out_the_cooldown_before_it_is_paid(market, monkeypatch):
    monkeypatch.setattr(settings, "payout_cooldown_hours", 24)
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    assert ship(market).status_code == 200
    assert payout_for(market.order["id"]) is None  # shipped, but the address is too new
    seller = sellers.by_code(market.code)
    sellers.update_seller(seller["id"], payout_verified_at=int(time.time()) - 25 * 3600)
    asyncio.run(fulfilment.sweep())
    assert payout_for(market.order["id"])["status"] == "SENT"


def test_a_dispute_holds_back_a_payout_that_is_still_waiting(market, monkeypatch):
    monkeypatch.setattr(settings, "payout_cooldown_hours", 24)
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    ship(market)
    market.buyer.post(
        f"/orders/{market.order['id']}/problem",
        json={"kind": "not_as_described", "message": "The box was empty when it arrived."},
    )
    seller = sellers.by_code(market.code)
    sellers.update_seller(seller["id"], payout_verified_at=int(time.time()) - 48 * 3600)
    asyncio.run(fulfilment.sweep())
    assert payout_for(market.order["id"]) is None  # paused while the problem is open


def test_buyers_see_trader_details_only_for_sellers_they_bought_from(market):
    market.run()
    info = market.buyer.get(f"/sellers/{market.code}").json()
    assert info["legal_name"] == "Shop Limited" and info["support_email"] == "help@shop.example"
    assert info["return_days"] == 30 and info["self_certified"] is True
    assert "pay@shop.example" not in str(info)  # payout details are never shown
    with TestClient(app) as stranger:
        sign_up(stranger, "stranger@example.com")
        assert stranger.get(f"/sellers/{market.code}").status_code == 404


def test_addresses_are_encrypted_owned_and_deletable(market):
    made = market.buyer.post("/addresses", json=ADDRESS).json()
    assert "Market Road" in made["line1"] and "phone" not in made
    with storage.get_store().engine.connect() as db:
        stored = db.execute(select(schema.delivery_addresses.c.ciphertext)).scalar()
    assert "Market Road" not in stored and "Bea" not in stored  # encrypted at rest
    with TestClient(app) as other:
        sign_up(other, "other@example.com")
        assert other.get("/addresses").json() == []
        assert other.post(f"/addresses/{made['id']}/delete").status_code == 404
    assert market.buyer.post(f"/addresses/{made['id']}/delete").status_code == 200
    assert market.buyer.get("/addresses").json() == []
    bad = market.buyer.post("/addresses", json={**ADDRESS, "country": "France"})
    assert bad.status_code == 422
    assert market.buyer.post("/addresses", json={**ADDRESS, "phone": "ring me"}).status_code == 422


def test_a_simulated_seller_still_pays_out_immediately_as_before(runtime):
    with TestClient(app) as buyer:
        sign_up(buyer, "buyer@example.com")
        hold_id = buy(buyer)
        buyer.post("/blocs/demo-success/start")
        books = wait_settled(buyer)
    assert books["reconciled"] is True and books["held_for_shipping"] == "0.00"
    assert orders.order_for_payment(ledger.by_order(hold_id)["id"]) is None
    assert money.payout_rows("demo-success")
