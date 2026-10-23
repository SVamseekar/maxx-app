"""Money layer: holds, partial capture, void, payouts, webhooks, idempotency and the real client."""

import asyncio
import json
import time
from decimal import Decimal

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.main import app
from maxx.money import ledger, service, webhooks
from maxx.money.paypal import PayPalClient, PayPalError
from maxx.money.simulator import SimulatedPayPal
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from tests.conftest import sign_up


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    monkeypatch.setattr(settings, "paypal_negative_testing", True)
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def hold(client, bloc="demo-success", price="150", test_case=""):
    order = client.post(
        f"/money/blocs/{bloc}/hold", json={"max_price": price, "test_case": test_case}
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]
    assert client.post(f"/money/holds/{order_id}/simulate-approve").status_code == 200
    joined = client.post(f"/money/holds/{order_id}/authorize")
    assert joined.status_code == 200, joined.text
    return order_id


def finish(client, bloc="demo-success"):
    assert client.post(f"/blocs/{bloc}/start").status_code == 202
    for _ in range(300):
        books = client.get(f"/money/blocs/{bloc}/ledger").json()
        if books["settlement"] in {"DONE", "PARTIAL"}:
            return books
        time.sleep(0.02)
    raise AssertionError("settlement did not finish")


def test_config_reports_mode_and_hides_secrets(runtime, monkeypatch):
    monkeypatch.setattr(settings, "paypal_client_secret", "shh-secret")
    with TestClient(app) as client:
        config = client.get("/money/config").json()
    assert config["mode"] == "simulator" and config["simulated"] is True
    assert "shh-secret" not in json.dumps(config)
    assert config["client_id"] == ""  # only sandbox mode exposes the (public) client id


def test_off_by_default_keeps_the_original_join(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "paypal_mode", "off")
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/off.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    try:
        with TestClient(app) as client:
            sign_up(client)
            assert (
                client.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code
                == 200
            )
            assert (
                client.post("/money/blocs/demo-success/hold", json={"max_price": "150"}).status_code
                == 404
            )
    finally:
        app.dependency_overrides.clear()


def test_joining_needs_an_approved_hold(runtime):
    with TestClient(app) as client:
        sign_up(client)
        direct = client.post("/blocs/demo-success/join", json={"max_price": "150"})
        assert direct.status_code == 402 and direct.json()["code"] == "payment_required"
        order_id = client.post("/money/blocs/demo-success/hold", json={"max_price": "150"}).json()[
            "order_id"
        ]
        # Not approved yet: nothing is held and nobody joined.
        early = client.post(f"/money/holds/{order_id}/authorize")
        assert early.status_code == 409
        assert not [
            m for m in client.get("/blocs/demo-success").json()["members"] if m["user_id"] == "me"
        ]
        client.post(f"/money/holds/{order_id}/simulate-approve")
        joined = client.post(f"/money/holds/{order_id}/authorize").json()
        assert any(m["user_id"] == "me" and m["status"] == "HELD" for m in joined["members"])
        payment = ledger.by_order(order_id)
        assert payment["status"] == "AUTHORIZED" and payment["simulated"]
        assert payment["authorization_id"].startswith("SIM-AUTH-")


def test_hold_rules_match_joining_rules(runtime):
    with TestClient(app) as client:
        sign_up(client)
        # Below 50% of the typical price is refused before PayPal is contacted.
        assert (
            client.post("/money/blocs/demo-success/hold", json={"max_price": "50"}).status_code
            == 409
        )
        assert client.post("/money/blocs/nope/hold", json={"max_price": "150"}).status_code == 404
        hold(client)
        again = client.post("/money/blocs/demo-success/hold", json={"max_price": "150"})
        assert again.status_code == 409  # already joined


def test_another_user_cannot_use_my_order(runtime):
    with TestClient(app) as mine, TestClient(app) as theirs:
        sign_up(mine, "a@example.com")
        sign_up(theirs, "b@example.com")
        order_id = mine.post("/money/blocs/demo-success/hold", json={"max_price": "150"}).json()[
            "order_id"
        ]
        assert theirs.post(f"/money/holds/{order_id}/simulate-approve").status_code == 404
        assert theirs.post(f"/money/holds/{order_id}/authorize").status_code == 404


def test_leaving_voids_the_hold(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        assert client.post("/blocs/demo-success/leave").status_code == 200
        assert ledger.by_order(order_id)["status"] == "VOIDED"
        assert client.get("/money/receipts").json()[0]["status"] == "VOIDED"


def test_cleared_bloc_captures_only_the_winning_price_and_holds_it_for_shipping(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        books = finish(client)
        payment = ledger.by_order(order_id)
        bloc = runtime.store.get("demo-success")
        mine = next(
            m
            for m in bloc.members
            if m.status == "WIN" and m.user_id != "x" and m.id == payment["member_id"]
        )
        assert payment["status"] == "CAPTURED"
        assert Decimal(payment["captured_amount"]) == mine.final_price
        assert Decimal(payment["captured_amount"]) <= Decimal(payment["max_amount"])
        assert payment["capture_id"].startswith("SIM-CAP-")
        # Books tie out: the captured money is held until the seller ships; nothing is paid yet.
        assert books["settlement"] == "DONE" and books["reconciled"] is True
        assert books["held_for_shipping"] == books["captured_total"]
        assert Decimal(books["platform_fee"]) == 0 and Decimal(books["seller_payouts"]) == 0
        receipt = client.get("/money/receipts").json()[0]
        assert receipt["status"] == "CAPTURED" and Decimal(receipt["saved"]) >= 0


def test_settlement_is_idempotent(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        finish(client)
        before = ledger.by_order(order_id)
        outcome = asyncio.run(service.settle_bloc(runtime.store, "demo-success"))
        assert outcome == {}  # already done: nothing to claim
        assert ledger.by_order(order_id) == before
        assert len(service.payout_rows("demo-success")) == len(
            {p["seller_id"] for p in service.payout_rows("demo-success")}
        )


def test_failed_bloc_voids_every_hold(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client, "demo-failure")
        books = finish(client, "demo-failure")
        assert ledger.by_order(order_id)["status"] == "VOIDED"
        assert books["captured_count"] == 0 and books["payouts"] == []


def test_declined_capture_is_recorded_not_hidden(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client, test_case="capture_declined")
        finish(client)
        payment = ledger.by_order(order_id)
        assert payment["status"] == "CAPTURE_FAILED" and payment["error"] == "INSTRUMENT_DECLINED"
        assert payment["captured_amount"] is None


def test_test_cases_are_ignored_unless_negative_testing_is_on(runtime, monkeypatch):
    monkeypatch.setattr(settings, "paypal_negative_testing", False)
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client, test_case="capture_declined")
        assert ledger.by_order(order_id)["meta"] == ""


def test_declined_authorization_means_no_membership(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order = client.post(
            "/money/blocs/demo-success/hold",
            json={"max_price": "150", "test_case": "authorize_declined"},
        ).json()
        client.post(f"/money/holds/{order['order_id']}/simulate-approve")
        assert client.post(f"/money/holds/{order['order_id']}/authorize").status_code == 409
        assert ledger.by_order(order["order_id"])["status"] == "FAILED"
        assert not [
            m for m in client.get("/blocs/demo-success").json()["members"] if m["user_id"] == "me"
        ]


def test_simulator_enforces_paypal_capture_rules(runtime):
    pp = SimulatedPayPal()

    async def scenario():
        order = await pp.create_order(Decimal("100"), "ref", "req-1")
        assert (await pp.create_order(Decimal("100"), "ref", "req-1"))["id"] == order["id"]
        with pytest.raises(PayPalError):  # not approved
            await pp.authorize_order(order["id"], "auth-1")
        pp.approve(order["id"])
        auth = await pp.authorize_order(order["id"], "auth-1")
        with pytest.raises(PayPalError) as over:
            await pp.capture_authorization(auth["authorization_id"], Decimal("100.01"), "cap-x")
        assert over.value.name == "CAPTURE_AMOUNT_EXCEEDED"
        first = await pp.capture_authorization(auth["authorization_id"], Decimal("80"), "cap-1")
        again = await pp.capture_authorization(auth["authorization_id"], Decimal("80"), "cap-1")
        assert first == again  # same request id, same capture
        with pytest.raises(PayPalError) as twice:
            await pp.capture_authorization(auth["authorization_id"], Decimal("10"), "cap-2")
        assert twice.value.name == "AUTHORIZATION_ALREADY_CAPTURED"

    asyncio.run(scenario())


def event(kind, resource, id="WH-1"):
    return json.dumps({"id": id, "event_type": kind, "resource": resource}).encode()


def test_webhooks_need_a_valid_signature_and_apply_once(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        authorization = ledger.by_order(order_id)["authorization_id"]
        body = event("PAYMENT.AUTHORIZATION.VOIDED", {"id": authorization})
        bad = client.post(
            "/money/webhooks/paypal",
            content=body,
            headers={"content-type": "application/json", "x-maxx-sim-signature": "0" * 64},
        )
        assert bad.status_code == 400
        assert ledger.by_order(order_id)["status"] == "AUTHORIZED"
        signed = {
            "content-type": "application/json",
            "x-maxx-sim-signature": webhooks.sign_simulated(body),
        }
        ok = client.post("/money/webhooks/paypal", content=body, headers=signed)
        assert ok.status_code == 200 and ok.json()["duplicate"] is False
        assert ledger.by_order(order_id)["status"] == "VOIDED"
        replay = client.post("/money/webhooks/paypal", content=body, headers=signed)
        assert replay.json()["duplicate"] is True
        # A tampered body no longer matches its signature.
        forged = event("PAYMENT.AUTHORIZATION.VOIDED", {"id": "x"}, id="WH-2")
        assert (
            client.post("/money/webhooks/paypal", content=forged, headers=signed).status_code == 400
        )


def test_webhook_cannot_raise_a_capture_above_the_hold(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        payment = ledger.by_order(order_id)
        body = event(
            "PAYMENT.CAPTURE.COMPLETED",
            {
                "id": payment["authorization_id"],
                "amount": {"value": "999.00", "currency_code": "USD"},
            },
        )
        client.post(
            "/money/webhooks/paypal",
            content=body,
            headers={
                "content-type": "application/json",
                "x-maxx-sim-signature": webhooks.sign_simulated(body),
            },
        )
        assert ledger.by_order(order_id)["status"] == "AUTHORIZED"


def test_webhook_route_is_off_when_payments_are_off(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "off")
    with TestClient(app) as client:
        assert client.post("/money/webhooks/paypal", json={}).status_code == 404


# ---- the real client, against a mock transport --------------------------------------------------


def make_client(handler):
    return PayPalClient(
        "https://api-m.sandbox.paypal.com", "id", "secret", httpx.MockTransport(handler)
    )


def test_real_client_sends_idempotent_authorize_and_partial_capture(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3000})
        if path == "/v2/checkout/orders":
            return httpx.Response(201, json={"id": "ORDER1", "status": "CREATED"})
        if path.endswith("/capture"):
            return httpx.Response(201, json={"id": "CAP1", "status": "COMPLETED"})
        raise AssertionError(path)

    pp = make_client(handler)

    async def go():
        order = await pp.create_order(Decimal("150"), "bloc-1", "order-req-1")
        capture = await pp.capture_authorization("AUTH1", Decimal("132.5"), "cap-req-1")
        return order, capture

    order, capture = asyncio.run(go())
    assert order["id"] == "ORDER1" and capture["capture_id"] == "CAP1"
    create = next(r for r in seen if r.url.path == "/v2/checkout/orders")
    body = json.loads(create.content)
    assert body["intent"] == "AUTHORIZE"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "150.00"}
    assert create.headers["paypal-request-id"] == "order-req-1"
    assert create.headers["authorization"] == "Bearer tok"
    cap = next(r for r in seen if r.url.path.endswith("/capture"))
    assert json.loads(cap.content) == {
        "amount": {"currency_code": "USD", "value": "132.50"},
        "final_capture": True,
    }
    assert cap.headers["paypal-request-id"] == "cap-req-1"
    assert sum(r.url.path == "/v1/oauth2/token" for r in seen) == 1  # token cached


def test_real_client_treats_an_already_voided_hold_as_released():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3000})
        return httpx.Response(
            422,
            json={
                "name": "UNPROCESSABLE_ENTITY",
                "details": [{"issue": "AUTHORIZATION_ALREADY_VOIDED"}],
            },
        )

    asyncio.run(make_client(handler).void_authorization("AUTH1", "void-1"))


def test_real_client_marks_server_errors_retryable():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3000})
        return httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE", "message": "later"})

    with pytest.raises(PayPalError) as error:
        asyncio.run(make_client(handler).capture_authorization("A", Decimal("1"), "r"))
    assert error.value.retryable is True


def test_real_client_verifies_webhooks_through_paypal(monkeypatch):
    monkeypatch.setattr(settings, "paypal_webhook_id", "WH-ID")
    sent = {}

    def handler(request: httpx.Request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3000})
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"verification_status": "SUCCESS"})

    headers = {
        "PayPal-Auth-Algo": "SHA256withRSA",
        "PayPal-Cert-Url": "https://api.sandbox.paypal.com/cert",
        "PayPal-Transmission-Id": "t1",
        "PayPal-Transmission-Sig": "sig",
        "PayPal-Transmission-Time": "2026-01-01T00:00:00Z",
    }
    body = event("PAYMENT.CAPTURE.COMPLETED", {"id": "C"})
    pp = make_client(handler)
    assert asyncio.run(pp.verify_webhook(headers, body)) is True
    assert sent["webhook_id"] == "WH-ID" and sent["webhook_event"]["id"] == "WH-1"
    # A missing header never reaches PayPal and never verifies.
    assert asyncio.run(pp.verify_webhook({}, body)) is False


def test_live_paypal_is_refused(monkeypatch):
    from maxx.hardening import configuration_problems

    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(settings, "paypal_base_url", "https://api-m.paypal.com")
    assert any("sandbox" in p for p in configuration_problems())
    monkeypatch.setattr(settings, "paypal_base_url", "https://api-m.sandbox.paypal.com")
    assert not any("sandbox" in p for p in configuration_problems())


def test_a_paypal_outage_during_settlement_resumes_without_double_capture(runtime, monkeypatch):
    real = SimulatedPayPal.capture_authorization
    calls = {"n": 0}

    async def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PayPalError("PayPal is down.", 503, "SERVICE_UNAVAILABLE", retryable=True)
        return await real(self, *args, **kwargs)

    monkeypatch.setattr(SimulatedPayPal, "capture_authorization", flaky)
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        books = finish(client)
        assert books["settlement"] == "PARTIAL"
        assert ledger.by_order(order_id)["status"] == "AUTHORIZED"  # untouched, not lost
        bloc = runtime.store.get("demo-success")
        assert service.needs_settlement(bloc)
        asyncio.run(service.settle_bloc(runtime.store, "demo-success"))
        payment = ledger.by_order(order_id)
        assert payment["status"] == "CAPTURED"
        assert client.get("/money/blocs/demo-success/ledger").json()["settlement"] == "DONE"
        # A third pass finds nothing left to do.
        assert asyncio.run(service.settle_bloc(runtime.store, "demo-success")) == {}
        assert service.payout_rows("demo-success") == []  # sellers are paid per shipped order


def test_a_demo_reset_releases_holds_for_the_replaced_bloc(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = hold(client)
        assert ledger.by_order(order_id)["status"] == "AUTHORIZED"
        assert client.post("/demo/reset").status_code == 200  # new generation; old Bloc is gone
        assert asyncio.run(service.release_orphans(runtime.store)) == 1
        assert ledger.by_order(order_id)["status"] == "VOIDED"
        assert asyncio.run(service.release_orphans(runtime.store)) == 0
