"""Tracking numbers, carrier updates and when a seller is paid for a shipped order."""

import asyncio
import json
import time

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from maxx.config import settings
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.fulfilment import tracking, tracking_numbers
from maxx.main import app
from maxx.notify import service as notify
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.test_fulfilment import Market, payout_for
from tests.test_fulfilment import runtime as runtime  # noqa: F401 - shared fixture

FORMATS = tracking_numbers.all_formats()


@pytest.mark.parametrize("name,fmt", FORMATS, ids=[f"{n}:{f['name']}" for n, f in FORMATS])
def test_every_vendored_sample_number_is_judged_as_the_data_expects(name, fmt):
    for number in fmt["tests"].get("valid", []):
        assert tracking_numbers.match_format(fmt, number) is True, number
    for number in fmt["tests"].get("invalid", []):
        assert tracking_numbers.match_format(fmt, number) is not True, number


def test_recognise_checks_the_carrier_and_the_check_digit():
    ups = tracking_numbers.recognise("ups", "1z999aa1 0123456784")
    assert ups and ups.number == "1Z999AA10123456784" and ups.checksum
    assert tracking_numbers.recognise("ups", "1Z999AA10123456785") is None  # one digit off
    assert tracking_numbers.recognise("fedex", "1Z999AA10123456784") is None  # wrong carrier
    assert tracking_numbers.recognise("royalmail", "RB123456785GB").kind == "S10"
    assert tracking_numbers.recognise("royalmail", "RB123456785XX") is None  # no such post
    assert tracking_numbers.recognise("other", "ANYTHING123") is None
    assert tracking_numbers.recognise("ups", "1Z" + "9" * 100) is None


@pytest.fixture
def tracked(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "tracking_mode", "simulator")
    monkeypatch.setattr(settings, "tracking_sim_step_seconds", 60)
    market = Market(runtime)
    market.run()
    market.buyer.post(
        f"/orders/{market.order['id']}/address", json={"address_id": market.address()}
    )
    yield market
    market.close()


def ship(market, number="1Z999AA10123456784", carrier="ups", order_id=None):
    return market.seller.post(
        f"/seller/orders/{order_id or market.order['id']}/ship",
        json={"carrier": carrier, "tracking": number},
    )


class Clock:
    """The simulated carrier's clock, moved forward without touching recorded event times."""

    def __init__(self):
        self.offset = 0.0

    def time(self) -> float:
        return time.time() + self.offset


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(tracking, "time", value)
    return value


def age(order_id: str, seconds: int, clock: Clock) -> None:
    """Let the simulated parcel travel for `seconds`, and make the next sweep look at it."""
    clock.offset += seconds
    orders.update_order(order_id, None, tracking_checked_at=0)


def test_a_malformed_or_reused_tracking_number_is_refused(tracked):
    refused = ship(tracked, "1Z999AA10123456785")
    assert refused.status_code == 409 and "check digit" in refused.json()["detail"]
    assert ship(tracked, "1Z999AA10123456784", carrier="dhl").status_code == 409
    assert ship(tracked, "123", carrier="pigeon").status_code == 409
    assert ship(tracked).status_code == 200
    # Another buyer's order may not reuse the same parcel number.
    with TestClient(app) as other:
        sign_up(other, "buyer2@example.com", "Cy Buyer")
        second = tracked.run("demo-flaky", other)
        other.post(f"/orders/{second['id']}/address", json={"address_id": tracked.address(other)})
        reused = ship(tracked, order_id=second["id"])
        assert reused.status_code == 409 and "already used" in reused.json()["detail"]


def test_a_new_seller_is_paid_on_delivery_not_on_shipping(tracked, clock):
    assert ship(tracked).status_code == 200
    order = orders.get_order(tracked.order["id"])
    assert order["tracker_id"].startswith("SIM-TRK-") and order["tracking_status"] == "pre_transit"
    assert payout_for(order["id"]) is None
    view = tracked.seller.get("/seller/orders").json()[0]
    assert view["payout_waiting"] == "Paid once the carrier scans the parcel."
    age(order["id"], 70, clock)  # picked up
    asyncio.run(fulfilment.sweep())
    order = orders.get_order(order["id"])
    assert order["tracking_status"] == "in_transit" and order["first_scan_at"]
    assert payout_for(order["id"]) is None  # new seller: waits for delivery
    age(order["id"], 130, clock)  # delivered
    asyncio.run(fulfilment.sweep())
    order = orders.get_order(order["id"])
    assert order["status"] == "DELIVERED" and order["tracking_status"] == "delivered"
    assert payout_for(order["id"])["status"] == "SENT"
    timeline = tracked.buyer.get("/orders").json()[0]
    assert [e["status"] for e in timeline["tracking_events"]][-1] == "delivered"
    assert timeline["tracking_simulated"] is True
    kinds = {n["kind"] for n in notify.inbox(tracked.buyer_user["id"])["items"]}
    assert {"order.won", "order.shipped", "order.delivered"} <= kinds


def test_an_established_seller_is_paid_at_the_first_carrier_scan(tracked, monkeypatch, clock):
    monkeypatch.setattr(settings, "payout_trusted_after_deliveries", 0)
    ship(tracked)
    asyncio.run(fulfilment.sweep())
    assert payout_for(tracked.order["id"]) is None  # label only, not scanned
    age(tracked.order["id"], 70, clock)
    asyncio.run(fulfilment.sweep())
    assert payout_for(tracked.order["id"])["status"] == "SENT"


def test_a_returned_parcel_holds_the_payout_until_a_person_clears_it(tracked, monkeypatch):
    monkeypatch.setattr(settings, "payout_trusted_after_deliveries", 0)
    assert ship(tracked, "EZ5000000005").status_code == 200  # simulator test code
    asyncio.run(fulfilment.sweep())
    order = orders.get_order(tracked.order["id"])
    assert order["tracking_status"] == "return_to_sender"
    assert "returned" in order["review_flag"] or "return" in order["review_flag"]
    assert payout_for(order["id"]) is None
    seller_kinds = {n["kind"] for n in notify.inbox(tracked.user["id"])["items"]}
    assert "seller.tracking_issue" in seller_kinds
    # A person checks with the carrier and releases it; the parcel is not flagged again.
    orders.update_order(order["id"], None, review_flag=fulfilment.CLEARED + "buyer refused it")
    assert asyncio.run(fulfilment.release_payout(order["id"])) == "SENT"
    orders.update_order(order["id"], None, tracking_checked_at=0)
    asyncio.run(fulfilment.sweep())
    assert orders.get_order(order["id"])["review_flag"].startswith(fulfilment.CLEARED)


def test_a_parcel_the_carrier_never_scans_is_flagged(tracked):
    ship(tracked, "EZ1000000001")  # stays at label created
    orders.update_order(
        tracked.order["id"], None, shipped_at=int(time.time()) - 5 * 86400, tracking_checked_at=0
    )
    asyncio.run(fulfilment.sweep())
    order = orders.get_order(tracked.order["id"])
    assert "not scanned" in order["review_flag"]
    assert payout_for(order["id"]) is None


def test_tracking_webhooks_are_only_a_hint_and_must_be_signed(tracked, monkeypatch):
    ship(tracked)
    order = orders.get_order(tracked.order["id"])
    forged = {
        "description": "tracker.updated",
        "result": {"id": order["tracker_id"], "status": "delivered"},
    }
    with TestClient(app) as provider:
        sent = provider.post("/webhooks/tracking", json=forged)
        assert sent.status_code == 202
    # The body said delivered, but the tracker was re-read from the provider: still pre-transit.
    assert orders.get_order(order["id"])["status"] == "SHIPPED"
    monkeypatch.setattr(settings, "easypost_webhook_secret", "whsec-test")
    with TestClient(app) as provider:
        assert provider.post("/webhooks/tracking", json=forged).status_code == 401
        body = json.dumps(forged).encode()
        import hashlib
        import hmac

        good = "hmac-sha256-hex=" + hmac.new(b"whsec-test", body, hashlib.sha256).hexdigest()
        signed = provider.post(
            "/webhooks/tracking",
            content=body,
            headers={"content-type": "application/json", "x-hmac-signature": good},
        )
        assert signed.status_code == 202


def test_easypost_trackers_are_created_and_read_with_the_server_key(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization", "")))
        if request.method == "POST":
            assert json.loads(request.content)["tracker"]["carrier"] == "UPS"
            return httpx.Response(201, json={"id": "trk_123", "status": "pre_transit"})
        return httpx.Response(
            200,
            json={
                "id": "trk_123",
                "status": "in_transit",
                "status_detail": "arrived_at_facility",
                "est_delivery_date": "2026-10-30T00:00:00Z",
                "carrier_detail": {"destination_tracking_location": {"country": "GB"}},
                "tracking_details": [
                    {
                        "status": "in_transit",
                        "message": "Arrived at facility",
                        "datetime": "2026-10-24T10:00:00Z",
                        "tracking_location": {"city": "Leeds", "country": "GB"},
                    }
                ],
            },
        )

    monkeypatch.setattr(settings, "tracking_mode", "easypost")
    monkeypatch.setattr(settings, "easypost_api_key", "EZTK-test-key")
    monkeypatch.setattr(tracking, "_transport", httpx.MockTransport(handler))
    tracker = asyncio.run(tracking.register("ups", "1Z999AA10123456784", "GB"))
    state = asyncio.run(tracking.fetch(tracker))
    assert tracker == "trk_123" and state.status == "in_transit"
    assert state.destination_country == "GB" and state.events[0]["location"] == "Leeds, GB"
    assert all(auth.startswith("Basic ") for _, _, auth in seen)


def test_a_payout_paypal_cannot_deliver_is_retried_after_the_seller_fixes_it(tracked):
    seller = sellers.by_code(tracked.code)
    sellers.update_seller(seller["id"], payout_email="pay@unclaimed.example")
    tracked_order = tracked.order["id"]
    ship(tracked)
    orders.update_order(tracked_order, None, status="DELIVERED", delivered_at=int(time.time()))
    assert asyncio.run(fulfilment.release_payout(tracked_order)) == "SENT"
    asyncio.run(fulfilment.refresh_payouts())  # PayPal reports the item unclaimed, then returned
    payout = payout_for(tracked_order)
    assert payout["item_status"] == "UNCLAIMED" and payout["status"] == "SENT"
    fulfilment.apply_payout_item(
        payout["paypal_batch_id"],
        {
            "payout_item_id": payout["payout_item_id"],
            "status": "RETURNED",
            "error": "RECEIVER_UNREGISTERED",
        },
    )
    assert payout_for(tracked_order)["status"] == "FAILED"
    assert "seller.payout_failed" in {n["kind"] for n in notify.inbox(tracked.user["id"])["items"]}
    # The seller confirms a working payout email; the failed payout goes out again to it.
    sellers.update_seller(seller["id"], payout_email="pay@shop.example")
    assert fulfilment.retry_failed_payouts(tracked.code) == 1
    assert asyncio.run(fulfilment.release_payout(tracked_order)) == "SENT"
    again = payout_for(tracked_order)
    assert again["attempt"] == 2 and again["receiver"] == "pay@shop.example"
    asyncio.run(fulfilment.refresh_payouts())
    assert payout_for(tracked_order)["item_status"] == "SUCCESS"
