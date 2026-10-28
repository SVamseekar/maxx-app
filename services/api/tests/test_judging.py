"""What a hackathon judge walks through: one-tap entry, a private copy of each demo scenario,
an honest room when live AI is unavailable, and a seller tour that can be replayed."""

import asyncio
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from maxx.auth import mail
from maxx.config import settings
from maxx.demo import tour
from maxx.fulfilment import service as fulfilment
from maxx.fulfilment import store as orders
from maxx.main import app
from maxx.notify import service as notify
from maxx.sellers import store as sellers
from tests.conftest import sign_up
from tests.marketplace import wait_settled
from tests.test_fulfilment import runtime as runtime  # noqa: F401 - shared fixture

CODE = "judge-code-for-tests-0001"


def test_judge_entry_is_off_without_a_code(runtime):  # noqa: F811
    with TestClient(app) as client:
        assert client.get("/auth/judge").json() == {"available": False}
        assert client.post("/auth/judge", json={"code": "anything"}).status_code == 404


def test_judge_entry_gives_each_judge_a_fresh_signed_in_account(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "judge_access_code", CODE)
    with TestClient(app) as one, TestClient(app) as two:
        assert one.get("/auth/judge").json() == {"available": True}
        assert one.post("/auth/judge", json={"code": "wrong"}).status_code == 403
        assert one.get("/auth/me").json()["user"] is None
        first = one.post("/auth/judge", json={"code": CODE})
        assert first.status_code == 200, first.text
        user = one.get("/auth/me").json()["user"]
        assert user["email_verified"] and user["email"].endswith(mail.JUDGE_DOMAIN)
        second = two.post("/auth/judge", json={"code": f"  {CODE} "}).json()["user"]
        assert second["id"] != user["id"]
    # Their notifications never try to reach a mailbox.
    sent = len(mail.outbox)
    asyncio.run(mail.deliver(user["email"], "Hello", "Body"))
    assert len(mail.outbox) == sent + 1  # recorded for tests, but no delivery attempted


def test_each_judge_gets_a_private_scenario_with_a_labelled_crowd(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "paypal_mode", "off")  # join without a hold
    with TestClient(app) as judge, TestClient(app) as other:
        sign_up(judge, "judge@example.com", "Jude")
        sign_up(other, "other@example.com", "Otto")
        assert judge.post("/demo/lab/nonsense").status_code == 404
        opened = judge.post("/demo/lab/success")
        assert opened.status_code == 201, opened.text
        bloc_id = opened.json()["bloc_id"]
        assert bloc_id.startswith("lab-success-")
        assert judge.post("/demo/lab/success").json()["bloc_id"] == bloc_id  # reused while open
        assert other.post("/demo/lab/success").json()["bloc_id"] != bloc_id
        listed = {row["id"] for row in judge.get("/blocs").json()}
        assert bloc_id not in listed and "demo-success" in listed
        view = judge.get(f"/blocs/{bloc_id}").json()
        assert view["viewer_is_owner"] and view["seller_count"] == 8
        assert len(view["members"]) == 600 and all(m["simulated"] for m in view["members"])
        joined = judge.post(f"/blocs/{bloc_id}/join", json={"max_price": "150"})
        assert joined.status_code == 200, joined.text
        mine = [m for m in joined.json()["members"] if m["user_id"] == "me"]
        assert len(mine) == 1 and not mine[0]["simulated"]


def test_live_negotiation_without_ai_runs_the_labelled_replay(runtime, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "nebius_api_key", "")
    monkeypatch.setattr(settings, "negotiation_replay_fallback", True)
    monkeypatch.setattr(settings, "paypal_mode", "off")
    runtime.mode = "live"
    with TestClient(app) as client:
        sign_up(client)
        assert client.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 200
        assert client.post("/blocs/demo-success/start").status_code == 202
        for _ in range(200):
            bloc = runtime.store.get("demo-success")
            if bloc.status in {"SETTLED", "FAILED"}:
                break
            time.sleep(0.01)
        assert bloc.status == "SETTLED" and bloc.mode == "fixture"
        notice = [e for e in bloc.events if e.type == "live_unavailable"]
        assert len(notice) == 1 and notice[0].data["message"]


@pytest.fixture
def tour_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "tracking_mode", "simulator")
    monkeypatch.setattr(settings, "simulated_seller_ship_seconds", 0)


def test_the_seller_tour_can_be_replayed_from_a_clean_shop(runtime, tour_on):  # noqa: F811
    with TestClient(app) as judge:
        sign_up(judge, "judge@example.com", "Jude")
        first = judge.post("/demo/seller-tour").json()["bloc_id"]
        wait_settled(judge, first)
        code = judge.get("/seller").json()["seller"]["code"]
        assert tour.act_for_demo_buyers() == 3
        # The judge walks away: the deadlines pass and every order is refunded, with no strike.
        for order in orders.orders_in(["AWAITING_SHIPMENT"]):
            orders.update_order(order["id"], None, ship_by=0)
        asyncio.run(fulfilment.sweep())
        demo = sellers.by_code(code)
        assert demo["strikes"] == 0 and demo["status"] == "ACTIVE"
        inbox = notify.inbox(demo["user_id"])["items"]
        assert not [n for n in inbox if n["kind"] in {"seller.strike", "seller.order_cancelled"}]
        # Even a shop suspended by strikes from an older build starts clean again.
        sellers.update_seller(
            demo["id"], strikes=5, status="SUSPENDED", review_note=tour.STRIKE_SUSPENSION
        )
        second = judge.post("/demo/seller-tour")
        assert second.status_code == 201, second.text
        demo = sellers.by_code(code)
        assert demo["strikes"] == 0 and demo["status"] == "ACTIVE"
        wait_settled(judge, second.json()["bloc_id"])
        assert tour.act_for_demo_buyers() == 3
        ready = [
            o for o in judge.get("/seller/orders").json() if o["status"] == "AWAITING_SHIPMENT"
        ]
        # Every demo order can use the same carrier test number.
        for order in ready[:2]:
            shipped = judge.post(
                f"/seller/orders/{order['id']}/ship",
                json={"carrier": "ups", "tracking": "EZ4000000004"},
            )
            assert shipped.status_code == 200, shipped.text


def test_an_administrators_suspension_survives_a_tour_restart(runtime, tour_on):  # noqa: F811
    with TestClient(app) as judge:
        sign_up(judge, "judge@example.com", "Jude")
        judge.post("/demo/seller-tour")
        code = judge.get("/seller").json()["seller"]["code"]
        demo = sellers.by_code(code)
        sellers.update_seller(demo["id"], status="SUSPENDED", review_note="Abuse of the demo.")
        asyncio.run(tour.fresh_start(sellers.by_code(code)))
        assert sellers.by_code(code)["status"] == "SUSPENDED"


def test_finished_blocs_of_other_people_leave_the_public_list(runtime, monkeypatch):  # noqa: F811
    from maxx.negotiate.blocs import make_bloc, transition

    monkeypatch.setattr(settings, "list_cache_seconds", 0)
    old = make_bloc("qa-old", "QA journey lamp, white", Decimal("50"))
    transition(old, "FAILED")
    runtime.store.create(old)
    with TestClient(app) as visitor:
        listed = {row["id"] for row in visitor.get("/blocs").json()}
    assert "qa-old" not in listed and {"demo-success", "demo-failure", "demo-flaky"} <= listed


def test_wrong_codes_never_use_up_the_shared_entry_allowance(runtime, monkeypatch):  # noqa: F811
    from maxx.auth import ratelimit

    monkeypatch.setattr(settings, "judge_access_code", CODE)
    before = ratelimit.count("judge-entry:all", 3600)
    with TestClient(app) as client:
        assert client.post("/auth/judge", json={"code": "wrong"}).status_code == 403
        assert ratelimit.count("judge-entry:all", 3600) == before
        assert client.post("/auth/judge", json={"code": CODE}).status_code == 200
    assert ratelimit.count("judge-entry:all", 3600) == before + 1
