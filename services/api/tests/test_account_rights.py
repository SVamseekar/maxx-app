"""Access, export and closing an account when money and orders are involved."""

import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.fulfilment import store as orders
from maxx.main import app
from maxx.money import ledger
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.marketplace import ADDRESS, buy
from tests.test_fulfilment import Market


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def close(client):
    return client.post("/auth/me/delete", json={"confirm": "delete my account"})


def test_export_contains_the_persons_data_and_no_secrets(runtime):
    with TestClient(app) as client:
        user = sign_up(client)
        client.post("/addresses", json=ADDRESS)
        buy(client)
        data = client.get("/me/export")
        assert data.status_code == 200 and "attachment" in data.headers["content-disposition"]
        body = data.json()
    assert body["account"]["email"] == user["email"]
    assert body["delivery_addresses"][0]["line1"] == "22 Market Road"
    assert body["payments"][0]["status"] == "AUTHORIZED"
    text = data.text
    assert (
        "scrypt" not in text
        and "password_hash" not in text
        and "totp" not in text.replace("two_step_enabled", "")
    )


def test_export_needs_a_recent_identity_check_and_a_session(runtime, monkeypatch):
    with TestClient(app) as anonymous:
        assert anonymous.get("/me/export").status_code == 401
    with TestClient(app) as client:
        sign_up(client)
        monkeypatch.setattr(settings, "reauth_minutes", -1)
        stale = client.get("/me/export")
        assert stale.status_code == 403 and stale.json()["code"] == "reauth_required"


def test_closing_an_account_releases_open_holds_and_erases_addresses(runtime):
    with TestClient(app) as client:
        sign_up(client)
        address = client.post("/addresses", json=ADDRESS).json()["id"]
        hold_id = buy(client)
        assert close(client).status_code == 204
        assert ledger.by_order(hold_id)["status"] == "VOIDED"  # nobody stays charged or held
    with TestClient(app) as other:
        sign_up(other, "other@example.com")
    assert address


def test_an_undelivered_order_blocks_closing_the_account(runtime):
    market = Market(runtime)
    try:
        market.run()
        refused = close(market.buyer)
        assert refused.status_code == 409 and "not been delivered" in refused.json()["detail"]
        assert close(market.seller).status_code == 409  # the seller has an order to ship
    finally:
        market.close()


def test_a_finished_order_lets_the_buyer_leave_and_wipes_their_address(runtime):
    market = Market(runtime)
    try:
        market.run()
        market.buyer.post(
            f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
        )
        market.seller.post(
            f"/seller/orders/{market.order['id']}/ship",
            json={"carrier": "UPS", "tracking": "TRACK12345"},
        )
        market.buyer.post(f"/orders/{market.order['id']}/delivered")
        assert close(market.buyer).status_code == 204
        assert orders.get_order(market.order["id"])["address_blob"] is None
        # The seller can finish and close too; their trader record is kept but closed.
        assert close(market.seller).status_code == 204
        record = sellers.by_code(market.code)
        assert record["status"] == "CLOSED" and record["payout_email"] == "closed"
        assert sellers.offers_for(record["id"]) == []
    finally:
        market.close()
