"""Seller verification: identity checks, sanctions screening, review and the INFORM Act rules."""

import asyncio
import hashlib
import hmac
import json
import time
from decimal import Decimal

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from maxx import schema, storage
from maxx.compliance import identity, sanctions
from maxx.config import settings
from maxx.main import app
from maxx.notify import service as notify
from maxx.sellers import lifecycle
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.marketplace import apply, code_sent_to, offer, onboard
from tests.test_fulfilment import runtime as runtime  # noqa: F401 - shared fixture


@pytest.fixture
def identity_on(monkeypatch):
    monkeypatch.setattr(settings, "verify_mode", "simulator")
    monkeypatch.setattr(settings, "seller_identity_required", True)


def test_a_seller_cannot_sell_until_their_identity_is_verified(runtime, identity_on):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com", "Sam Seller")
        profile = onboard(client)
        assert profile["status"] == "PENDING"
        assert profile["compliance"]["next_step"] == "identity"
        assert offer(client).status_code == 409
        started = client.post("/seller/identity/start").json()
        assert started["simulated"] and started["url"].startswith("/sell/verify-identity?session=")
        session = started["url"].split("session=")[1]
        with TestClient(app) as stranger:
            sign_up(stranger, "x@example.com")
            onboard(stranger, "x@shop.example")
            stolen = stranger.post(
                "/seller/identity/simulate", json={"session": session, "outcome": "verified"}
            )
            assert stolen.status_code == 404  # a session belongs to its own seller
        failed = client.post(
            "/seller/identity/simulate", json={"session": session, "outcome": "failed"}
        ).json()
        assert failed["compliance"]["identity_status"] == "requires_input"
        assert failed["status"] == "PENDING"
        session = client.post("/seller/identity/start").json()["url"].split("session=")[1]
        done = client.post(
            "/seller/identity/simulate", json={"session": session, "outcome": "verified"}
        ).json()
        assert done["status"] == "ACTIVE" and done["compliance"]["identity_status"] == "verified"
        assert offer(client).status_code == 200
        kinds = {n["kind"] for n in client.get("/notifications").json()["items"]}
        assert {"seller.identity", "seller.status"} <= kinds


def test_a_sanctions_match_sends_the_seller_to_a_person(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    with TestClient(app) as client, TestClient(app) as boss:
        sign_up(client, "seller@example.com", "Sam Seller")
        sign_up(boss, "boss@example.com", "Boss")
        profile = onboard(client, legal_name="Banco Nacional de Cuba")
        assert profile["status"] == "UNDER_REVIEW"
        assert profile["compliance"]["next_step"] == "screening"
        assert "BANCO" not in json.dumps(profile)  # the seller is never told what matched
        assert offer(client).status_code == 409
        pending = boss.get("/admin/overview").json()["pending_sellers"]
        assert pending[0]["screening_hits"][0]["name"] == "BANCO NACIONAL DE CUBA"
        approve = boss.post(
            f"/admin/sellers/{profile['code']}/decision", json={"action": "approve"}
        )
        assert approve.status_code == 409  # screening first
        cleared = boss.post(
            f"/admin/sellers/{profile['code']}/screening",
            json={"decision": "clear", "note": "Different company; checked the register."},
        ).json()
        assert cleared["screening_status"] == "clear" and cleared["status"] == "ACTIVE"
        # A cleared match is not raised again for the same list entry.
        assert lifecycle.screen(sellers.by_code(profile["code"])) == "clear"


def test_blocking_a_match_suspends_the_seller_for_good(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    with TestClient(app) as client, TestClient(app) as boss:
        sign_up(client, "seller@example.com")
        sign_up(boss, "boss@example.com", "Boss")
        code = onboard(client, legal_name="National Bank of Cuba")["code"]
        blocked = boss.post(
            f"/admin/sellers/{code}/screening",
            json={"decision": "block", "note": "Confirmed match against the SDN list."},
        ).json()
        assert blocked["status"] == "SUSPENDED" and blocked["screening_status"] == "blocked"
        again = boss.post(
            f"/admin/sellers/{code}/decision", json={"action": "reinstate", "note": "try"}
        )
        assert again.status_code == 409


def test_screening_waits_when_the_list_has_never_been_loaded(runtime):  # noqa: F811
    from maxx import audit

    audit.set_flag(sanctions.VERSION_FLAG, "")
    with storage.get_store().engine.begin() as db:
        db.execute(schema.system_flags.delete())
    with TestClient(app) as client:
        sign_up(client, "seller@example.com")
        profile = onboard(client)
        assert profile["status"] == "UNDER_REVIEW"  # nobody is cleared against an empty list
    sanctions.load('1,"SOMEONE ELSE",-0-,"X",-0-\n', "", "test")
    lifecycle.sweep_compliance()
    assert sellers.by_code(profile["code"])["status"] == "ACTIVE"


def test_names_are_matched_generously_but_one_shared_word_is_not_a_match():
    assert sanctions.screen(["Banko Nacionale de Kuba"])[0].entry_id == "306"
    assert sanctions.screen(["Shop Ltd"]) == []
    assert sanctions.screen(["Trading Company of Cuba Ltd"]) == []
    assert sanctions.screen(["Mohammed Ali"])  # common names go to a person, by design


def stripe_signature(body: bytes, secret: str, stamp: int | None = None) -> str:
    stamp = stamp or int(time.time())
    mac = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={mac}"


def test_stripe_webhooks_need_a_fresh_valid_signature(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    body = b'{"type":"identity.verification_session.verified"}'
    assert identity.verify_webhook(stripe_signature(body, "whsec_test"), body)
    assert not identity.verify_webhook(stripe_signature(body, "whsec_other"), body)
    assert not identity.verify_webhook(stripe_signature(body + b" ", "whsec_test"), body)
    stale = stripe_signature(body, "whsec_test", int(time.time()) - 3600)
    assert not identity.verify_webhook(stale, body)
    assert not identity.verify_webhook("", body)


def test_a_stripe_identity_result_is_read_back_from_stripe(runtime, monkeypatch):  # noqa: F811
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer sk_test_123"
        if request.method == "POST":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            assert form["type"] == "document"
            return httpx.Response(
                200, json={"id": "vs_123", "url": "https://verify.stripe.com/start/abc"}
            )
        return httpx.Response(
            200,
            json={
                "id": "vs_123",
                "status": "verified",
                "verified_outputs": {
                    "first_name": "Sam",
                    "last_name": "Seller",
                    "address": {"country": "GB"},
                },
            },
        )

    monkeypatch.setattr(settings, "verify_mode", "stripe")
    monkeypatch.setattr(settings, "seller_identity_required", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    monkeypatch.setattr(identity, "_transport", httpx.MockTransport(handler))
    with TestClient(app) as client, TestClient(app) as stripe:
        sign_up(client, "seller@example.com", "Sam Seller")
        onboard(client, legal_name="Sam Seller", business_type="individual")
        started = client.post("/seller/identity/start").json()
        assert started["url"] == "https://verify.stripe.com/start/abc"
        event = json.dumps(
            {
                "type": "identity.verification_session.verified",
                "data": {"object": {"id": "vs_123", "status": "verified"}},
            }
        ).encode()
        unsigned = stripe.post(
            "/webhooks/identity", content=event, headers={"content-type": "application/json"}
        )
        assert unsigned.status_code == 401
        signed = stripe.post(
            "/webhooks/identity",
            content=event,
            headers={
                "content-type": "application/json",
                "stripe-signature": stripe_signature(event, "whsec_test"),
            },
        )
        assert signed.status_code == 202
        profile = client.get("/seller").json()["seller"]
        assert profile["compliance"]["identity_status"] == "verified"
        assert profile["status"] == "ACTIVE"
    assert any(r.method == "GET" and "expand" in str(r.url) for r in requests)


def test_an_individual_whose_id_name_differs_is_reviewed(runtime, identity_on):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com", "Sam Seller")
        code = onboard(client, legal_name="Totally Different Person", business_type="individual")[
            "code"
        ]
        seller = sellers.by_code(code)
        session, _ = asyncio.run(identity.start(seller))
        sellers.update_seller(seller["id"], identity_session=session)
        identity.simulate_outcome(session, seller["id"], True, "Sam Seller")
        result = asyncio.run(identity.fetch(session))
        fresh = lifecycle.apply_identity(sellers.by_code(code), result)
        assert fresh["status"] == "UNDER_REVIEW" and fresh["screening_status"] == "review"


def test_a_high_volume_seller_must_give_a_tax_id_or_stop_selling(runtime):  # noqa: F811
    with TestClient(app) as client:
        user = sign_up(client, "seller@example.com", "Sam Seller")
        code = onboard(client)["code"]
    seller = sellers.by_code(code)
    with storage.get_store().engine.begin() as db:
        for i in range(settings.high_volume_sales):
            db.execute(
                schema.orders.insert().values(
                    id=f"o{i}",
                    payment_id=f"p{i}",
                    bloc_id="b",
                    generation=1,
                    buyer_id="someone",
                    seller_code=code,
                    seller_user_id=user["id"],
                    title="Lamp",
                    amount=Decimal("30.00"),
                    currency="USD",
                    status="DELIVERED",
                    ship_by=0,
                    created_at=int(time.time()),
                    updated_at=int(time.time()),
                )
            )
    assert lifecycle.sweep_compliance()["high_volume"] == 1
    seller = sellers.by_code(code)
    assert seller["info_due_by"] and lifecycle.can_sell(seller)
    assert "seller.info_required" in {n["kind"] for n in notify.inbox(user["id"])["items"]}
    sellers.update_seller(seller["id"], info_due_by=int(time.time()) - 1)
    assert not lifecycle.can_sell(sellers.by_code(code))
    seller = sellers.by_code(code)
    lifecycle.record_certification(seller, "GB 123 456 789")
    seller = sellers.by_code(code)
    assert lifecycle.can_sell(seller) and seller["tax_id_last4"] == "6789"
    with storage.get_store().engine.connect() as db:
        stored = db.execute(
            select(schema.sellers.c.tax_id_enc).where(schema.sellers.c.code == code)
        ).scalar()
    assert "123456789" not in stored  # encrypted at rest


def test_an_overdue_yearly_certification_pauses_new_sales(runtime):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com")
        code = onboard(client)["code"]
        seller = sellers.by_code(code)
        late = int(time.time()) - (settings.seller_info_days + 1) * 86400
        sellers.update_seller(seller["id"], recertify_by=late)
        assert offer(client).status_code == 409
        renewed = client.post("/seller/compliance", json={"certify": True})
        assert renewed.status_code == 200 and renewed.json()["compliance"]["can_sell"] is True
        assert offer(client).status_code == 200


def test_the_payout_email_code_is_bound_to_the_address(runtime):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com")
        assert apply(client).status_code == 201
        code = code_sent_to("pay@shop.example")
        wrong = client.post(
            "/seller/payout-verify", json={"code": f"{(int(code) + 1) % 10**6:06d}"}
        )
        assert wrong.status_code == 400


def test_provider_settings_that_cannot_work_are_refused(monkeypatch):
    from maxx.hardening import configuration_problems

    monkeypatch.setattr(settings, "tracking_mode", "carrier-pigeon")
    monkeypatch.setattr(settings, "verify_mode", "stripe")
    problems = " ".join(configuration_problems())
    assert "TRACKING_MODE must be" in problems and "STRIPE_SECRET_KEY" in problems
    monkeypatch.setattr(settings, "tracking_mode", "easypost")
    monkeypatch.setattr(settings, "verify_mode", "off")
    monkeypatch.setattr(settings, "seller_identity_required", True)
    problems = " ".join(configuration_problems())
    assert "EASYPOST_API_KEY" in problems and "SELLER_IDENTITY_REQUIRED" in problems


def test_closing_a_seller_account_removes_its_identity_and_tax_details(runtime, identity_on):  # noqa: F811
    with TestClient(app) as client:
        sign_up(client, "seller@example.com", "Sam Seller")
        code = onboard(client)["code"]
        session = client.post("/seller/identity/start").json()["url"].split("session=")[1]
        client.post("/seller/identity/simulate", json={"session": session, "outcome": "verified"})
        lifecycle.record_certification(sellers.by_code(code), "123456789")
        exported = client.get("/me/export").json()
        assert exported["seller_verification"]["identity_status"] == "verified"
        assert "123456789" not in json.dumps(exported)  # only the last four digits
        assert (
            client.post("/auth/me/delete", json={"confirm": "delete my account"}).status_code == 204
        )
    closed = sellers.by_code(code)
    assert closed["status"] == "CLOSED" and closed["identity_name"] == ""
    assert closed["tax_id_enc"] is None and closed["identity_session"] is None
