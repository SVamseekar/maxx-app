"""Maxx Plus: premium switches on and off only through webhook events."""

import json

import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.main import app
from maxx.money import subscriptions, webhooks
from tests.conftest import sign_up
from tests.test_checkout import body, row


@pytest.fixture(autouse=True)
def payments(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")


def test_requires_sign_in_and_lists_plans():
    with TestClient(app) as client:
        assert client.get("/money/subscription").status_code == 401
        sign_up(client)
        status = client.get("/money/subscription").json()
    assert [p["id"] for p in status["plans"]] == ["weekly", "yearly"]
    assert status["premium"] is False and status["checkout_limit"] == "500"


def test_subscribing_does_nothing_until_paypal_confirms():
    with TestClient(app) as client:
        user = sign_up(client)
        assert client.post("/money/subscription", json={"plan": "weekly"}).status_code == 200
        pending = client.get("/money/subscription").json()
        assert (
            pending["subscription"]["status"] == "APPROVAL_PENDING" and pending["premium"] is False
        )
        client.post("/money/subscription/simulate-approve")
        active = client.get("/money/subscription").json()
        assert active["premium"] is True and active["checkout_limit"] == "2000"
        assert subscriptions.is_premium(user["id"])
        assert client.post("/money/subscription", json={"plan": "yearly"}).status_code == 409


def test_cancelling_turns_premium_off():
    with TestClient(app) as client:
        sign_up(client)
        client.post("/money/subscription", json={"plan": "yearly"})
        client.post("/money/subscription/simulate-approve")
        assert client.post("/money/subscription/cancel").status_code == 200
        status = client.get("/money/subscription").json()
        assert status["premium"] is False and status["subscription"]["status"] == "CANCELLED"


def test_a_forged_activation_is_rejected_by_the_signature_check():
    with TestClient(app) as client:
        sign_up(client)
        sub = client.post("/money/subscription", json={"plan": "weekly"}).json()
        event = json.dumps(
            {
                "id": "WH-X",
                "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                "resource": {"id": sub["id"]},
            }
        ).encode()
        forged = client.post(
            "/money/webhooks/paypal", content=event, headers={"content-type": "application/json"}
        )
        assert forged.status_code == 400
        assert client.get("/money/subscription").json()["premium"] is False
        signed = client.post(
            "/money/webhooks/paypal",
            content=event,
            headers={
                "content-type": "application/json",
                "x-maxx-sim-signature": webhooks.sign_simulated(event),
            },
        )
        assert signed.status_code == 200
        assert client.get("/money/subscription").json()["premium"] is True


def test_premium_raises_the_agent_checkout_limit():
    pricey = body(row("700.00", "5.00"), current="900.00")
    with TestClient(app) as client:
        sign_up(client)
        assert client.post("/checkout/propose", json=pricey).status_code == 409
        client.post("/money/subscription", json={"plan": "weekly"})
        client.post("/money/subscription/simulate-approve")
        offer = client.post("/checkout/propose", json=pricey)
        assert offer.status_code == 200 and offer.json()["total"] == "705.00"
