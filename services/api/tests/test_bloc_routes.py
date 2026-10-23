import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from maxx.main import app
from maxx.negotiate.blocs import add_member, make_bloc, transition
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from maxx.negotiate.stream import event_frames
from tests.conftest import sign_up


@pytest.fixture
def runtime(tmp_path):
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def test_join_leave_start_outcome_and_redaction(runtime):
    with TestClient(app) as client:
        b = client.get("/blocs/demo-success").json()
        assert b["mode"] == "fixture"
        assert "sellers" not in b
        assert client.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 401
        sign_up(client)
        joined = client.post("/blocs/demo-success/join", json={"max_price": "150"})
        assert joined.status_code == 200
        assert client.post("/blocs/demo-success/leave").status_code == 200
        assert client.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 200
        assert client.post("/blocs/demo-success/start").status_code == 202
        # Background execution is drained on runtime close; snapshot polling is bounded.
        for _ in range(100):
            b = client.get("/blocs/demo-success").json()
            if b["status"] in ["SETTLED", "FAILED"]:
                break
            import time

            time.sleep(0.01)
        assert b["status"] == "SETTLED"
        you = [m for m in b["members"] if m["user_id"] == "me" and m["status"] != "LEFT"][0]
        assert you["status"] == "WIN"
        assert Decimal(you["final_price"]) <= Decimal(you["max_price"])
        assert client.post("/blocs/demo-success/start").status_code == 202  # no second auction
        with TestClient(app) as late:
            sign_up(late, "late2@example.com")
            assert (
                late.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 409
            )
        assert "floor" not in str(b)


def test_failed_outcome_and_sse_replay(runtime):
    b = runtime.store.get("demo-failure")
    transition(b, "NEGOTIATING")
    runtime.store.save(b)
    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.runner import run_negotiation

    asyncio.run(run_negotiation(runtime.store, b.id, FixtureAdapter(), round_delay=0))
    with TestClient(app) as client:
        result = client.get("/blocs/demo-failure").json()
        assert result["status"] == "FAILED"
        assert all(m["status"] == "RELEASED" for m in result["members"])
        last = result["events"][-2]["id"]
        response = client.get(f"/blocs/demo-failure/stream?after={last}")
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"type":"failed"' in response.text
        assert f"id: {last}\n" not in response.text
        assert client.get("/blocs/demo-failure/stream?after=999999").status_code == 409
        assert client.get("/blocs/missing").status_code == 404


def test_stream_generates_new_persisted_events_and_terminal_close(tmp_path):
    store = BlocStore(f"sqlite:///{tmp_path}/stream.sqlite")
    b = make_bloc("stream", "Headphones", Decimal("200"))
    add_member(b, "you", "150")
    transition(b, "NEGOTIATING")
    store.create(b)

    async def run():
        from maxx.negotiate.adapters import FixtureAdapter
        from maxx.negotiate.runner import run_negotiation

        runner = asyncio.create_task(
            run_negotiation(store, b.id, FixtureAdapter(), round_delay=0.02)
        )
        frames = []
        async for frame in event_frames(store, b.id, after=len(b.events), interval=0.001):
            frames.append(frame)
        await runner
        return frames

    frames = asyncio.run(run())
    assert any("round_start" in f for f in frames)
    assert "cleared" in frames[-1]
    ids = [int(f.splitlines()[0].split(": ")[1]) for f in frames if f.startswith("id:")]
    assert ids == sorted(set(ids))


def test_restart_recovers_interrupted_negotiation_and_reset_preserves_custom(runtime):
    b = runtime.store.get("demo-success")
    transition(b, "NEGOTIATING")
    runtime.store.save(b)
    with TestClient(app) as client:
        assert client.post("/demo/reset").status_code == 401
        sign_up(client)
        assert client.post("/demo/reset").status_code == 409
    runtime.recover()
    assert runtime.store.get(b.id).status == "FAILED"
    custom = make_bloc("custom", "Custom product", Decimal("200"))
    runtime.store.create(custom)
    with TestClient(app) as client:
        sign_up(client, "second@example.com")
        assert client.post("/demo/reset").status_code == 200
        assert client.get("/blocs/custom").status_code == 200
        assert client.get("/blocs/demo-success").json()["status"] == "OPEN"


def test_live_mode_never_falls_back_when_key_missing(runtime, monkeypatch):
    from maxx.config import settings

    monkeypatch.setattr(settings, "nebius_api_key", "")
    runtime.mode = "live"
    with TestClient(app) as client:
        sign_up(client)
        assert client.post("/blocs/demo-success/start").status_code == 403  # not a member
        assert client.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 200
        result = client.post("/blocs/demo-success/start")
        assert result.status_code == 503
        assert runtime.store.get("demo-success").status == "OPEN"


def test_cold_runtime_factory_is_serialized(monkeypatch, tmp_path):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from maxx import storage
    from maxx.negotiate import routes

    factory = BlocStore
    calls = []
    lock = threading.Lock()

    def counted(url):
        with lock:
            calls.append(url)
        time.sleep(0.03)
        return factory(url)

    if hasattr(routes.get_runtime, "cache_clear"):
        routes.get_runtime.cache_clear()
    monkeypatch.setattr(routes, "_runtime", None, raising=False)
    monkeypatch.setattr(storage, "get_store", lambda: counted(f"sqlite:///{tmp_path}/cold.sqlite"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: routes.get_runtime(), range(2)))
    assert first is second
    assert len(calls) == 1


def test_catalogue_match_confirmation_and_demand_persistence(runtime):
    from maxx.matching import FixtureMatcher, get_matcher

    app.dependency_overrides[get_matcher] = FixtureMatcher
    with TestClient(app) as client:
        sign_up(client)
        item = {"title": "Sony headphones"}
        match = client.post("/catalog/match", json=item)
        assert match.status_code == 200
        assert match.json()["requires_confirmation"]
        key = match.json()["candidates"][0]["product_key"]
        body = {
            "title": "Sony headphones",
            "typical_price": "200",
            "item": item,
            "product_key": key,
        }
        assert client.post("/blocs", json=body).status_code == 409
        body["confirmed_variant"] = True
        created = client.post("/blocs", json=body)
        assert created.status_code == 201
        assert created.json()["product_key"] == key
        # Confirmed identity groups demand into the existing open Bloc.
        assert client.post("/blocs", json=body).json()["id"] == created.json()["id"]
        signals = runtime.store.demand_signals()
        assert len(signals) == 2 and signals[0]["confirmed"] is True
        body["product_key"] = "made-up"
        assert client.post("/blocs", json=body).status_code == 409


def test_catalogue_creation_does_not_reuse_expired_open_bloc(runtime, monkeypatch):
    from maxx.matching import FixtureMatcher, get_matcher

    monkeypatch.setattr("time.time", lambda: 1000)
    app.dependency_overrides[get_matcher] = FixtureMatcher
    body = {
        "title": "Sony WH-1000XM5 Black",
        "typical_price": "200",
        "item": {"title": "Sony WH-1000XM5 Black"},
        "product_key": "sony-wh1000xm5-black",
    }
    with TestClient(app) as client:
        sign_up(client)
        original = client.post("/blocs", json=body).json()
        expired = runtime.store.get(original["id"])
        expired.closes_at = 1000
        runtime.store.save(expired)

        response = client.post("/blocs", json=body)
        assert response.status_code == 201
        fresh = response.json()
        assert fresh["id"] != expired.id
        assert fresh["closes_at"] > 1000
        assert (
            client.post(f"/blocs/{fresh['id']}/join", json={"max_price": "150"}).status_code == 200
        )
        assert runtime.store.get(expired.id).closes_at == 1000
        # Subsequent demand still groups into the new, joinable Bloc.
        assert client.post("/blocs", json=body).json()["id"] == fresh["id"]
