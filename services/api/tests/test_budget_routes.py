"""Every AI call is charged to the person or pool that caused it, and a used-up budget pauses
live AI with a clear message while the rest of the app keeps working."""

import asyncio
from decimal import Decimal

import pytest
from conftest import sign_up
from fastapi.testclient import TestClient
from test_scan_guards import live_scan

from maxx import budget
from maxx.config import settings
from maxx.main import app
from maxx.providers import BudgetExceeded


def scopes():
    from sqlalchemy import select

    from maxx import schema, storage

    with storage.get_store().engine.connect() as db:
        rows = db.execute(select(schema.ai_budget.c.scope, schema.ai_budget.c.spent_micros))
        return {scope: spent for scope, spent in rows}


def test_an_anonymous_scan_is_charged_to_the_visitor_pool_and_their_address(monkeypatch):
    response, _ = live_scan(monkeypatch, {})
    assert response.status_code == 200
    charged = scopes()
    assert charged["anon_day"] > 0 and charged["day"] > 0 and charged["total"] > 0
    assert any(s.startswith("ip_day:") for s in charged)
    assert not any(s.startswith("user_day:") for s in charged)
    assert "testclient" not in str(charged)  # the address is stored only as a keyed hash


def test_a_signed_in_scan_is_charged_to_that_person(monkeypatch):
    client = TestClient(app)
    user = sign_up(client)
    response, _ = live_scan(monkeypatch, {}, client=client)
    assert response.status_code == 200
    charged = scopes()
    assert charged["user_day:" + user["id"]] > 0
    assert "anon_day" not in charged


def test_a_used_up_budget_pauses_live_ai_but_not_the_app(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", "0")
    response, seen = live_scan(monkeypatch, {})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "ai_paused"
    assert body["message"] == (
        "Live AI is paused: today's AI budget is used up. It resets at 00:00 UTC."
    )
    assert seen == {}  # no model was called at all
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/blocs").status_code == 200


def test_running_out_halfway_keeps_what_was_read_and_says_why(monkeypatch):
    monkeypatch.setattr(settings, "ai_max_calls_per_scan", 3)  # vision, normalise, then refused
    response, _ = live_scan(monkeypatch, {})
    result = response.json()
    assert response.status_code == 200
    assert result["item"]["price"] == "100.00"
    assert any(w.startswith("Live AI is paused:") for w in result["warnings"])


def test_visitors_can_be_asked_to_sign_in_before_any_live_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_anonymous_live", False)
    response, seen = live_scan(monkeypatch, {})
    assert response.status_code == 503
    assert response.json()["message"] == "Live AI is paused: sign in to use live AI."
    assert seen == {}


def test_fixture_scans_never_touch_the_budget(monkeypatch):
    import hashlib
    import json

    from maxx.config import ROOT

    monkeypatch.setattr(settings, "scan_mode", "fixture")
    monkeypatch.setattr(settings, "ai_paused", True)
    case = json.loads((ROOT / "evals/fixtures.json").read_text())[0]
    data = (ROOT / "evals" / case["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == case["sha256"]
    response = TestClient(app).post("/scan", content=data, headers={"content-type": "image/png"})
    assert response.status_code == 200
    assert scopes() == {}


def test_a_live_negotiation_needs_room_for_its_worst_case_before_it_starts(monkeypatch, tmp_path):
    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.routes import Runtime
    from maxx.negotiate.store import BlocStore

    class Live(FixtureAdapter):
        mode = "live"

    runtime = Runtime(BlocStore(f"sqlite:///{tmp_path}/r.sqlite"), "live", 0, Live)
    runtime.seed()
    monkeypatch.setattr(settings, "ai_daily_budget_usd", "0.05")
    with pytest.raises(BudgetExceeded, match="not enough of today's AI budget"):
        asyncio.run(runtime.start("demo-success"))
    assert runtime.store.get("demo-success").status == "OPEN"


def test_fixture_negotiations_never_touch_the_budget(tmp_path):
    from test_negotiation import setup_bloc

    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.runner import run_negotiation

    store = setup_bloc(tmp_path)
    asyncio.run(run_negotiation(store, "test", FixtureAdapter(), round_delay=0))
    assert store.get("test").status == "SETTLED"
    assert scopes() == {}


def test_catalogue_matching_is_metered_and_rate_limited(monkeypatch):
    import httpx2 as httpx

    from maxx import matching

    monkeypatch.setattr(settings, "match_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "k")
    vector = [{"index": i, "embedding": [1.0, float(i)]} for i in range(51)]
    original = httpx.AsyncClient
    monkeypatch.setattr(
        matching.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200, json={"data": vector, "usage": {"prompt_tokens": 500}}
                )
            ),
            **kw,
        ),
    )
    monkeypatch.setattr(settings, "match_rate_per_hour", 2)
    client = TestClient(app)
    for _ in range(2):
        assert client.post("/catalog/match", json={"title": "Sony"}).status_code == 200
    assert client.post("/catalog/match", json={"title": "Sony"}).status_code == 429
    assert scopes()["anon_day"] > 0


def test_people_can_see_what_is_left_of_their_allowance(monkeypatch):
    client = TestClient(app)
    anonymous = client.get("/ai/usage").json()
    assert anonymous["payer"] == "anonymous"
    assert Decimal(anonymous["remaining_usd"]) == Decimal("0.02")
    sign_up(client)
    signed_in = client.get("/ai/usage").json()
    assert signed_in["payer"] == "user"
    assert Decimal(signed_in["remaining_usd"]) == Decimal("0.05")
    assert signed_in["paused"] is False


def test_budget_status_lists_every_shared_limit():
    view = budget.status()
    assert set(view) >= {"total", "day", "anonymous_day", "tavily_month", "tavily_day", "paused"}


def test_a_call_with_no_payer_is_refused_not_charged_to_nobody():
    import contextvars

    def unscoped():
        return budget.reserve("r", "vision", Decimal("0.001"))

    with pytest.raises(BudgetExceeded, match="no payer"):
        contextvars.Context().run(unscoped)


def test_a_timed_close_without_budget_fails_and_releases_buyers(monkeypatch, tmp_path):
    import time

    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.routes import Runtime
    from maxx.negotiate.store import BlocStore

    class Live(FixtureAdapter):
        mode = "live"

    runtime = Runtime(BlocStore(f"sqlite:///{tmp_path}/r.sqlite"), "live", 0, Live)
    runtime.seed()
    bloc = runtime.store.get("demo-success")
    bloc.closes_at = int(time.time()) - 1
    runtime.store.save(bloc)
    monkeypatch.setattr(settings, "ai_daily_budget_usd", "0")
    asyncio.run(runtime.tick())
    closed = runtime.store.get("demo-success")
    assert closed.status == "FAILED"
    assert closed.failure_reason.startswith("Live AI is paused:")


def test_an_operator_pause_never_fails_a_timed_close(monkeypatch, tmp_path):
    import time

    from maxx import audit
    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.routes import Runtime
    from maxx.negotiate.store import BlocStore

    class Live(FixtureAdapter):
        mode = "live"

    runtime = Runtime(BlocStore(f"sqlite:///{tmp_path}/r.sqlite"), "live", 0, Live)
    runtime.seed()
    bloc = runtime.store.get("demo-success")
    bloc.closes_at = int(time.time()) - 1
    runtime.store.save(bloc)
    audit.set_flag("ai_paused", "1")
    asyncio.run(runtime.tick())
    assert runtime.store.get("demo-success").status == "OPEN"  # retried once AI resumes


def test_starting_and_creating_blocs_is_rate_limited_per_person(monkeypatch):
    monkeypatch.setattr(settings, "bloc_actions_per_hour", 2)
    client = TestClient(app)
    sign_up(client)
    body = {"title": "Custom headphones", "typical_price": "100", "confirmed_variant": True}
    codes = [client.post("/blocs", json=body).status_code for _ in range(3)]
    assert codes[:2] == [201, 201] and codes[2] == 429


def test_catalogue_matching_follows_the_sign_in_rule(monkeypatch):
    monkeypatch.setattr(settings, "match_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "k")
    monkeypatch.setattr(settings, "ai_anonymous_live", False)
    import httpx2 as httpx

    from maxx import matching

    sent = []
    original = httpx.AsyncClient
    monkeypatch.setattr(
        matching.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda req: sent.append(req) or httpx.Response(500)),
            **kw,
        ),
    )
    response = TestClient(app).post("/catalog/match", json={"title": "Sony"})
    assert sent == []
    assert response.status_code == 503
    assert "sign in to use live AI" in response.json()["detail"]


def test_a_negotiation_is_always_charged_to_a_responsible_person(monkeypatch, tmp_path):
    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.routes import Runtime
    from maxx.negotiate.store import BlocStore

    seen = []

    class Live(FixtureAdapter):
        mode = "live"

        async def negotiator(self, context):
            seen.append(budget.current().payer.owner)
            return await super().negotiator(context)

    from maxx.negotiate import routes

    async def no_market(*args):
        return None

    monkeypatch.setattr(routes, "refresh_market", no_market)
    runtime = Runtime(BlocStore(f"sqlite:///{tmp_path}/r.sqlite"), "live", 0, Live)
    runtime.seed()
    # A demo Bloc has no creator: the person who starts it is charged.
    asyncio.run(runtime.start("demo-success", starter="u-starter"))
    asyncio.run(runtime.tick())
    for _ in range(50):
        if runtime.store.get("demo-success").status != "NEGOTIATING":
            break
        asyncio.run(asyncio.sleep(0.05))
    assert set(seen) == {"u-starter"}
    from maxx.negotiate.routes import negotiation_owner

    bloc = runtime.store.get("demo-failure")
    assert negotiation_owner(bloc) == "origin:demand"  # a timed close of an ownerless Bloc
    bloc.owner_id = "u-owner"
    assert negotiation_owner(bloc) == "u-owner"
