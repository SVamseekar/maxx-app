"""The operator console: seller review, disputes, the brake. Administrators only."""

import pytest
from fastapi.testclient import TestClient

from maxx import audit
from maxx.config import settings
from maxx.main import app
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from maxx.sellers import store
from tests.conftest import sign_up
from tests.marketplace import onboard


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "simulator")
    monkeypatch.setattr(settings, "seller_review", "manual")
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    with TestClient(app) as client:
        sign_up(client, "boss@example.com", "The Boss")
        yield client


def test_only_administrators_can_open_the_console(runtime, admin):
    with TestClient(app) as normal:
        sign_up(normal, "someone@example.com")
        for path in ("/admin/overview", "/admin/audit", "/admin/reconcile"):
            assert normal.get(path).status_code == 403
        assert normal.post("/admin/payments/freeze", json={"frozen": True}).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.get("/admin/overview").status_code == 401
    assert admin.get("/admin/overview").status_code == 200


def test_review_queue_approve_reject_suspend_and_reinstate(runtime, admin):
    with TestClient(app) as seller:
        sign_up(seller, "sam@example.com")
        profile = onboard(seller)
        code = profile["code"]
        assert profile["status"] == "UNDER_REVIEW"
        queue = admin.get("/admin/overview").json()["pending_sellers"]
        assert [s["code"] for s in queue] == [code]
        assert queue[0]["legal_name"] == "Shop Limited" and "pay@shop.example" not in str(queue)
        approved = admin.post(
            f"/admin/sellers/{code}/decision", json={"action": "approve", "note": "Checked."}
        )
        assert approved.json()["status"] == "ACTIVE"
        assert seller.get("/seller/offers").status_code == 200
        assert (
            admin.post(f"/admin/sellers/{code}/decision", json={"action": "approve"}).status_code
            == 409
        )
        suspended = admin.post(
            f"/admin/sellers/{code}/decision", json={"action": "suspend", "note": "Complaints."}
        )
        assert suspended.json()["status"] == "SUSPENDED"
        assert seller.get("/seller/offers").status_code == 403
        back = admin.post(f"/admin/sellers/{code}/decision", json={"action": "reinstate"})
        assert back.json()["status"] == "ACTIVE" and back.json()["strikes"] == 0


def test_rejection_is_final_for_the_applicant_and_explained(runtime, admin):
    with TestClient(app) as seller:
        sign_up(seller, "sam@example.com")
        code = onboard(seller)["code"]
        admin.post(
            f"/admin/sellers/{code}/decision",
            json={"action": "reject", "note": "Could not verify business."},
        )
        again = seller.get("/seller/offers")
        assert again.status_code == 403
        overview = seller.get("/seller").json()["seller"]
        assert overview["status"] == "REJECTED" and "verify" in overview["review_note"]
        assert seller.post("/seller/payout-verify", json={"code": "123456"}).status_code == 403


def test_decisions_are_audited(runtime, admin):
    with TestClient(app) as seller:
        sign_up(seller, "sam@example.com")
        code = onboard(seller)["code"]
        admin.post(f"/admin/sellers/{code}/decision", json={"action": "approve", "note": "ok"})
    entry = next(e for e in audit.recent(50) if e["action"] == "seller.approve")
    assert entry["subject"] == code and entry["actor"].startswith("admin:")
    assert store.by_code(code)["reviewed_by"]


def test_freeze_and_thaw_the_money_with_an_audit_entry(runtime, admin):
    assert admin.get("/admin/overview").json()["payments_frozen"] is False
    assert (
        admin.post("/admin/payments/freeze", json={"frozen": True}).json()["payments_frozen"]
        is True
    )
    assert audit.payments_frozen() is True
    assert (
        admin.post("/admin/payments/freeze", json={"frozen": False}).json()["payments_frozen"]
        is False
    )
    assert [e["detail"] for e in audit.recent(5) if e["action"] == "payments.freeze"][:2] == [
        "thawed",
        "frozen",
    ]


def test_admin_can_settle_a_dispute_and_the_overview_shows_health(runtime, admin, monkeypatch):
    from tests.test_fulfilment import Market

    monkeypatch.setattr(settings, "seller_review", "auto")  # the seller goes live at once
    market = Market(runtime)
    try:
        market.run()
        market.buyer.post(
            f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
        )
        market.seller.post(
            f"/seller/orders/{market.order['id']}/ship",
            json={"carrier": "ups", "tracking": "1Z999AA10123456784"},
        )
        case = market.buyer.post(
            f"/orders/{market.order['id']}/problem",
            json={"kind": "not_as_described", "message": "The item does not match the listing."},
        ).json()["case_id"]
        overview = admin.get("/admin/overview").json()
        assert overview["open_cases"][0]["id"] == case and overview["health"]["failed_payouts"] == 0
        declined = admin.post(
            f"/admin/cases/{case}/resolve", json={"refund": False, "note": "Matches the listing."}
        )
        assert declined.json()["status"] == "RESOLVED_DECLINED"
        assert (
            admin.post(
                f"/admin/cases/{case}/resolve", json={"refund": True, "note": "Again"}
            ).status_code
            == 409
        )
        assert admin.get("/admin/reconcile").json()["mismatches"] == []
    finally:
        market.close()
