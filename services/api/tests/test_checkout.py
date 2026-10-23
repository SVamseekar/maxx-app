"""Agentic checkout: proposal rules, the guard, confirmation and capture."""

import time

import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.main import app
from maxx.money import checkout, ledger
from tests.conftest import sign_up


@pytest.fixture(autouse=True)
def payments(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")


def row(price="120.00", shipping="5.00", host="shop.example", **extra):
    base = {
        "title": "Headphones",
        "url": f"https://{host}/p",
        "price": price,
        "shipping": shipping,
        "same_item": True,
        "in_stock": True,
        "evidence": "Price $120.00",
    }
    return {**base, **extra}


def body(*rows, current="150.00", qty=1):
    return {"item_title": "Headphones", "qty": qty, "current_price": current, "rows": list(rows)}


def test_agent_tools_match_paypal_agent_toolkit_names():
    with TestClient(app) as client:
        names = [t["name"] for t in client.get("/checkout/tools").json()["tools"]]
    assert names == ["create_order", "get_order", "capture_order"]


def test_propose_picks_the_cheapest_verified_delivered_price():
    with TestClient(app) as client:
        sign_up(client)
        offer = client.post(
            "/checkout/propose",
            json=body(
                row("100.00", "40.00", "pricey.example"),
                row("118.00", "5.00", "good.example"),
                row("90.00", "5.00", "unverified.example", same_item=False),
                row("80.00", "5.00", "nostock.example", in_stock=False),
                row("70.00", None, "noshipping.example"),
            ),
        ).json()
    assert offer["merchant"] == "good.example" and offer["total"] == "123.00"
    assert offer["saves"] == "27.00"
    assert [step["tool"] for step in offer["plan"]] == [
        "create_order",
        "get_order",
        "capture_order",
    ]


def test_nothing_to_buy_when_no_offer_is_cheaper_or_trustworthy():
    with TestClient(app) as client:
        sign_up(client)
        dearer = client.post("/checkout/propose", json=body(row("150.00", "5.00")))
        assert dearer.status_code == 409 and "cheaper" in dearer.json()["detail"]
        none = client.post("/checkout/propose", json=body(row(same_item=False)))
        assert none.status_code == 409


def test_order_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "checkout_max_amount", "100")
    with TestClient(app) as client:
        sign_up(client)
        assert client.post("/checkout/propose", json=body(row("120.00", "5.00"))).status_code == 409


def test_confirm_requires_the_exact_total_and_a_genuine_offer():
    with TestClient(app) as client:
        sign_up(client)
        offer = client.post("/checkout/propose", json=body(row())).json()
        token = offer["proposal_token"]
        wrong = client.post(
            "/checkout/confirm", json={"proposal_token": token, "confirm_total": "10.00"}
        )
        assert (
            wrong.status_code == 409
            and ledger.for_user(client.get("/auth/me").json()["user"]["id"]) == []
        )
        forged = client.post(
            "/checkout/confirm",
            json={"proposal_token": token[:-4] + "AAAA", "confirm_total": "125.00"},
        )
        assert forged.status_code == 409


def test_offer_cannot_be_used_by_someone_else_or_after_it_expires(monkeypatch):
    with TestClient(app) as mine, TestClient(app) as theirs:
        sign_up(mine, "a@example.com")
        sign_up(theirs, "b@example.com")
        token = mine.post("/checkout/propose", json=body(row())).json()["proposal_token"]
        stolen = theirs.post(
            "/checkout/confirm", json={"proposal_token": token, "confirm_total": "125.00"}
        )
        assert stolen.status_code == 409
        real = time.time
        monkeypatch.setattr(time, "time", lambda: real() + 3600)
        late = mine.post(
            "/checkout/confirm", json={"proposal_token": token, "confirm_total": "125.00"}
        )
        assert late.status_code == 409 and "expired" in late.json()["detail"]


def test_full_flow_charges_once_and_only_after_approval():
    with TestClient(app) as client:
        user = sign_up(client)
        token = client.post("/checkout/propose", json=body(row())).json()["proposal_token"]
        confirm = {"proposal_token": token, "confirm_total": "125.00"}
        order = client.post("/checkout/confirm", json=confirm).json()
        assert order["amount"] == "125.00" and order["reused"] is False
        # The same confirmation again must not create a second order.
        assert (
            client.post("/checkout/confirm", json=confirm).json()["order_id"] == order["order_id"]
        )
        early = client.post(f"/checkout/orders/{order['order_id']}/capture")
        assert (
            early.status_code == 409 and ledger.by_order(order["order_id"])["status"] == "CREATED"
        )
        client.post(f"/money/holds/{order['order_id']}/simulate-approve")
        done = client.post(f"/checkout/orders/{order['order_id']}/capture").json()
        assert done["status"] == "COMPLETED" and done["capture_id"].startswith("SIM-CAP-")
        assert (
            client.post(f"/checkout/orders/{order['order_id']}/capture").json()["capture_id"]
            == done["capture_id"]
        )
        payment = ledger.by_order(order["order_id"])
        assert payment["status"] == "CAPTURED" and str(payment["captured_amount"]) == "125.00"
        receipts = client.get("/money/receipts").json()
        assert receipts[0]["kind"] == "checkout" and receipts[0]["title"] == "Headphones"
        assert user["id"] == payment["user_id"]


def test_guard_refuses_a_mismatched_amount():
    proposal = {"total": "125.00"}
    with pytest.raises(checkout.Refused):
        checkout.guard(proposal, "125.00", amount=__import__("decimal").Decimal("125.05"))
    assert str(checkout.guard(proposal, "125.00")) == "125.00"
