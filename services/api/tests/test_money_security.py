"""Money hardening: limits, emergency brake, reauth, webhook replay, audit, self-dealing."""

import asyncio
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from maxx import audit
from maxx.config import settings
from maxx.main import app
from maxx.money import ledger, service, webhooks
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from tests.conftest import sign_up
from tests.marketplace import buy, offer, onboard, wait_settled


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def hold(client, price, bloc="demo-success"):
    return client.post(f"/money/blocs/{bloc}/hold", json={"max_price": price})


def test_a_single_hold_has_a_ceiling(runtime, monkeypatch):
    monkeypatch.setattr(settings, "hold_max_amount", "120")
    with TestClient(app) as client:
        sign_up(client)
        refused = hold(client, "150")
        assert refused.status_code == 409 and "limited" in refused.json()["detail"]
        assert hold(client, "110").status_code == 200


def test_total_open_holds_per_account_are_capped(runtime, monkeypatch):
    monkeypatch.setattr(settings, "hold_outstanding_max_per_user", "250")
    with TestClient(app) as client:
        sign_up(client)
        buy(client, "demo-success", "150")
        over = hold(client, "150", "demo-failure")
        assert over.status_code == 409 and "total" in over.json()["detail"]
        assert hold(client, "100", "demo-failure").status_code == 200


def test_number_of_open_holds_is_capped(runtime, monkeypatch):
    monkeypatch.setattr(settings, "hold_open_max_per_user", 1)
    with TestClient(app) as client:
        sign_up(client)
        buy(client)
        assert hold(client, "150", "demo-failure").status_code == 409


def test_the_emergency_brake_stops_new_holds_and_captures_but_keeps_holds_safe(
    runtime, monkeypatch
):
    with TestClient(app) as client:
        sign_up(client)
        order_id = buy(client)
        audit.set_flag("payments_frozen", "1")
        try:
            frozen = hold(client, "100", "demo-failure")
            assert frozen.status_code == 409 and "paused" in frozen.json()["detail"]
            client.post("/blocs/demo-success/start")
            books = wait_settled(client)
            assert books["settlement"] == "PARTIAL"  # captures wait, nothing is lost
            assert ledger.by_order(order_id)["status"] == "AUTHORIZED"
        finally:
            audit.set_flag("payments_frozen", "0")
        asyncio.run(service.settle_bloc(runtime.store, "demo-success"))
        assert ledger.by_order(order_id)["status"] == "CAPTURED"


def test_large_holds_need_a_recent_identity_check(runtime, monkeypatch):
    monkeypatch.setattr(settings, "hold_reauth_over", "100")
    with TestClient(app) as client:
        user = sign_up(client)
        assert hold(client, "150").status_code == 200  # just signed in
        monkeypatch.setattr(settings, "reauth_minutes", -1)
        stale = hold(client, "150", "demo-failure")
        assert stale.status_code == 403 and stale.json()["code"] == "reauth_required"
        assert hold(client, "100", "demo-failure").status_code == 200  # at the threshold is fine
        assert user["email"]


def test_a_seller_cannot_buy_their_own_product(runtime):
    with TestClient(app) as client:
        sign_up(client)
        onboard(client)
        offer(client)
        refused = hold(client, "150")
        assert refused.status_code == 409
        assert "cannot buy" in refused.json()["detail"]


def test_money_moves_leave_an_audit_trail(runtime):
    with TestClient(app) as client:
        sign_up(client)
        buy(client)
        client.post("/blocs/demo-success/start")
        wait_settled(client)
    actions = {row["action"] for row in audit.recent(200)}
    assert {"hold.placed", "payment.captured"} <= actions
    assert all(len(row["detail"]) <= 300 for row in audit.recent(200))


def signed(event: dict):
    body = json.dumps(event).encode()
    return body, {
        "content-type": "application/json",
        "x-maxx-sim-signature": webhooks.sign_simulated(body),
    }


def test_replayed_webhooks_older_than_three_days_are_refused(runtime):
    with TestClient(app) as client:
        body, headers = signed(
            {"id": "WH-OLD", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "x"}}
        )
        old = {**headers, "paypal-transmission-time": "2020-01-01T00:00:00Z"}
        assert client.post("/money/webhooks/paypal", content=body, headers=old).status_code == 400
        future = {**headers, "paypal-transmission-time": "2999-01-01T00:00:00Z"}
        assert (
            client.post("/money/webhooks/paypal", content=body, headers=future).status_code == 400
        )
        fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ok = client.post(
            "/money/webhooks/paypal",
            content=body,
            headers={**headers, "paypal-transmission-time": fresh},
        )
        assert ok.status_code == 200


def test_bad_signatures_are_recorded_but_cannot_flood_the_log(runtime):
    with TestClient(app) as client:
        body = b'{"id":"WH-X","event_type":"PAYMENT.CAPTURE.COMPLETED","resource":{"id":"x"}}'
        for _ in range(20):
            client.post(
                "/money/webhooks/paypal",
                content=body,
                headers={"content-type": "application/json", "x-maxx-sim-signature": "0" * 64},
            )
    rejected = [r for r in audit.recent(200) if r["action"] == "webhook.rejected"]
    assert 1 <= len(rejected) <= 5


def test_reconcile_against_paypal_finds_a_ledger_that_drifted(runtime):
    with TestClient(app) as client:
        sign_up(client)
        order_id = buy(client)
        assert asyncio.run(service.verify_remote())["mismatches"] == []
        # Someone voided the hold on PayPal's side without telling us.
        payment = ledger.by_order(order_id)
        from maxx.money.paypal import get_paypal

        asyncio.run(get_paypal().void_authorization(payment["authorization_id"], "drift"))
        drift = asyncio.run(service.verify_remote())
        assert drift["mismatches"] and drift["mismatches"][0]["paypal"] == "VOIDED"


def test_log_lines_never_carry_credentials(monkeypatch, caplog):
    from maxx.hardening import SecretFilter

    monkeypatch.setattr(settings, "paypal_client_secret", "super-secret-value-123")
    record = logging.LogRecord(
        "x",
        logging.INFO,
        "f",
        1,
        "calling with super-secret-value-123 and Authorization: Bearer A21AAKabcdefghijklmnop",
        (),
        None,
    )
    SecretFilter().filter(record)
    assert "super-secret-value-123" not in record.msg and "A21AAKabcdef" not in record.msg
    assert "[redacted]" in record.msg


def test_the_audit_log_is_not_writable_through_the_api(runtime):
    with TestClient(app) as client:
        sign_up(client)
        assert client.post("/admin/audit", json={}).status_code in {403, 404, 405}
        assert client.get("/admin/audit").status_code == 403  # administrators only
