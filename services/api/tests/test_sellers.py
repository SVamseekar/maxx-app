"""Seller onboarding: apply, verify the payout address, review, publish standing offers."""

import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.main import app
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from maxx.sellers import store
from tests.conftest import sign_up
from tests.marketplace import KEY, apply, code_sent_to, offer, onboard


@pytest.fixture
def runtime(tmp_path):
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def test_overview_lists_terms_prohibited_items_and_the_fee(runtime):
    with TestClient(app) as client:
        assert client.get("/seller").status_code == 401
        sign_up(client)
        data = client.get("/seller").json()
    assert data["seller"] is None and len(data["terms"]) >= 6 and data["fee_percent"] == "5"
    assert any("Cryptocurrency" in item for item in data["prohibited"])
    assert any("not ship" in term for term in data["terms"])  # Maxx is not the shipper
    assert data["min_return_days"] == 14 and "GB" in data["countries"]


def test_application_is_validated_like_a_marketplace_trader_check(runtime):
    with TestClient(app) as client:
        sign_up(client)
        assert apply(client, accept_terms=False).status_code == 422
        assert apply(client, certify_lawful=False).status_code == 422
        assert apply(client, certify_authorised=False).status_code == 422
        assert apply(client, payout="nope").status_code == 422
        assert apply(client, support_email="nope").status_code == 422
        assert apply(client, return_days=7).status_code == 422  # below the legal minimum
        assert apply(client, country="ZZ").status_code == 422
        assert apply(client, ships_to=["XX"]).status_code == 422
        assert apply(client, ships_to=[]).status_code == 422
        assert apply(client, website="http://insecure.example").status_code == 422
        assert apply(client, phone="call me").status_code == 422
        assert apply(client, ship_within_days=30).status_code == 422
        # EU companies must give a trade register number (Digital Services Act art. 30).
        assert apply(client, country="DE", trade_register_no="").status_code == 422
        ok = apply(client, country="DE", business_type="individual", trade_register_no="")
        assert ok.status_code == 201


def test_applying_emails_a_code_to_the_payout_address_and_masks_it(runtime):
    with TestClient(app) as client:
        sign_up(client)
        created = apply(client)
        assert created.status_code == 201
        profile = created.json()
        assert profile["status"] == "PENDING" and profile["payout_verified"] is False
        assert "pay@shop.example" not in str(profile)
        assert code_sent_to("pay@shop.example")
        assert apply(client).status_code == 409  # one seller account per person


def test_unverified_email_cannot_apply(runtime):
    with TestClient(app) as client:
        user = sign_up(client)
        from maxx.auth import store as accounts

        accounts.update_user(user["id"], email_verified=False)
        assert apply(client).status_code == 403


def test_console_stays_closed_until_the_payout_address_is_verified(runtime):
    with TestClient(app) as client:
        sign_up(client)
        assert client.get("/seller/offers").status_code == 409
        apply(client)
        assert client.get("/seller/offers").status_code == 409
        assert offer(client).status_code == 409
        assert client.post("/seller/payout-verify", json={"code": "000000"}).status_code == 400
        code = code_sent_to("pay@shop.example")
        ok = client.post("/seller/payout-verify", json={"code": code})
        assert ok.status_code == 200 and ok.json()["status"] == "ACTIVE"
        assert client.get("/seller/offers").json() == []
        assert client.post("/seller/payout-verify", json={"code": code}).status_code == 400


def test_manual_review_waits_for_an_administrator(runtime, monkeypatch):
    monkeypatch.setattr(settings, "seller_review", "manual")
    with TestClient(app) as client:
        user = sign_up(client)
        profile = onboard(client)
        assert profile["status"] == "UNDER_REVIEW"
        blocked = client.get("/seller/offers")
        assert blocked.status_code == 409 and "review" in blocked.json()["detail"]
        # Not live in any Bloc while under review.
        seller = store.by_user(user["id"])
        assert store.attach(runtime.store.get("demo-success").model_copy(deep=True)) == 0
        assert seller["status"] == "UNDER_REVIEW"


def test_a_code_for_another_address_does_not_verify(runtime):
    with TestClient(app) as client:
        sign_up(client)
        apply(client, "first@shop.example")
        first = code_sent_to("first@shop.example")
        client.post("/seller/payout-email", json={"payout_email": "second@shop.example"})
        assert client.post("/seller/payout-verify", json={"code": first}).status_code == 400
        second = code_sent_to("second@shop.example")
        assert client.post("/seller/payout-verify", json={"code": second}).status_code == 200


def test_verification_attempts_are_rate_limited(runtime):
    with TestClient(app) as client:
        sign_up(client)
        apply(client)
        statuses = [
            client.post("/seller/payout-verify", json={"code": f"{i:06d}"}).status_code
            for i in range(12)
        ]
    assert 429 in statuses and statuses[0] == 400


def test_commitments_can_be_updated_but_not_below_the_legal_minimum(runtime):
    with TestClient(app) as client:
        sign_up(client)
        onboard(client)
        body = {
            "ship_within_days": 2,
            "ships_to": ["GB"],
            "return_days": 21,
            "return_policy": "Free returns within 21 days, unused and in the box.",
            "support_email": "new@shop.example",
            "phone": "+44 20 7946 1111",
            "website": "",
        }
        ok = client.post("/seller/commitments", json=body)
        assert ok.status_code == 200 and ok.json()["return_days"] == 21
        assert (
            client.post("/seller/commitments", json={**body, "return_days": 3}).status_code == 422
        )


def test_opportunities_show_demand_without_naming_buyers(runtime):
    with TestClient(app) as client:
        sign_up(client)
        onboard(client)
        rows = client.get("/seller/opportunities").json()
    demo = next(r for r in rows if r["product_key"] == KEY)
    assert demo["buyers"] >= 600 and demo["curve"] and demo["my_offer"] is None
    assert "user" not in str(demo).lower()


def test_offer_rules(runtime):
    with TestClient(app) as client:
        sign_up(client)
        onboard(client)
        assert offer(client, opening_price="90.00").status_code == 422  # below floor
        assert offer(client, product_key="no such product").status_code == 404
        assert offer(client, floor="900.00", opening_price="950.00").status_code == 422
        assert offer(client, stock=0).status_code == 422
        assert offer(client, strategy="reckless").status_code == 422
        first = offer(client).json()
        again = offer(client, stock=80).json()  # same product: updated, not duplicated
        assert again["id"] == first["id"] and again["stock"] == 80
        assert len(client.get("/seller/offers").json()) == 1
        paused = client.post(f"/seller/offers/{first['id']}/active", json={"active": False})
        assert paused.json()["active"] is False


def test_one_seller_cannot_touch_anothers_offer(runtime):
    with TestClient(app) as mine, TestClient(app) as theirs:
        sign_up(mine, "a@example.com")
        sign_up(theirs, "b@example.com")
        onboard(mine, "a@shop.example")
        onboard(theirs, "b@shop.example")
        mine_offer = offer(mine).json()
        stolen = theirs.post(f"/seller/offers/{mine_offer['id']}/active", json={"active": False})
        assert stolen.status_code == 404


def test_only_verified_active_sellers_join_a_bloc(runtime):
    with TestClient(app) as client:
        user = sign_up(client)
        onboard(client)
        first = offer(client).json()
        bloc = runtime.store.get("demo-success")
        assert store.attach(bloc.model_copy(deep=True)) == 1
        seller = store.by_user(user["id"])
        store.update_seller(seller["id"], status="SUSPENDED")
        assert store.attach(bloc.model_copy(deep=True)) == 0
        store.update_seller(seller["id"], status="ACTIVE", payout_verified=False)
        assert store.attach(bloc.model_copy(deep=True)) == 0
        store.update_seller(seller["id"], payout_verified=True)
        client.post(f"/seller/offers/{first['id']}/active", json={"active": False})
        assert store.attach(bloc.model_copy(deep=True)) == 0  # paused offer sits out


def test_changing_the_payout_address_takes_the_seller_out_until_verified(runtime):
    with TestClient(app) as client:
        user = sign_up(client)
        onboard(client)
        offer(client)
        client.post("/seller/payout-email", json={"payout_email": "new@shop.example"})
        assert store.attach(runtime.store.get("demo-success").model_copy(deep=True)) == 0
        assert store.payout_receiver(store.by_user(user["id"])["code"]) is None
        client.post("/seller/payout-verify", json={"code": code_sent_to("new@shop.example")})
        assert store.payout_receiver(store.by_user(user["id"])["code"]) == "new@shop.example"
