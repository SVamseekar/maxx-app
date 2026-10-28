import asyncio
import json
from decimal import Decimal

from fastapi.testclient import TestClient

from maxx import storage
from maxx.config import ROOT, settings
from maxx.main import app
from maxx.negotiate.blocs import add_member, make_bloc, transition
from maxx.negotiate.routes import Runtime
from maxx.negotiate.store import BlocStore


def test_cache_expires_exactly_at_six_hours_and_survives_restart(tmp_path):
    url = f"sqlite:///{tmp_path}/cache.sqlite"
    first = BlocStore(url)
    first.cache_put("product-black", [{"price": "150"}], now=100)
    reopened = BlocStore(url)
    assert reopened.cache_get("product-black", now=21699) == [{"price": "150"}]
    assert reopened.cache_get("product-black", now=21700) is None
    assert reopened.cache_get("product-silver", now=101) is None


def test_queued_job_dispatch_and_event_replay_survive_restart(tmp_path):
    url = f"sqlite:///{tmp_path}/durable.sqlite"
    first = BlocStore(url)
    b = make_bloc("pending", "Headphones", Decimal("200"))
    add_member(b, "you", "150")
    first.create(b)
    transition(b, "NEGOTIATING")
    first.save(b, queue=True)
    reopened = BlocStore(url)
    runtime = Runtime(reopened, delay=0)
    runtime.recover()
    assert reopened.job_status(b.id) == "QUEUED"

    async def run():
        await runtime.tick()
        await asyncio.gather(*runtime.tasks.values())

    asyncio.run(run())
    final = reopened.get(b.id)
    assert final.status == "SETTLED"
    assert reopened.job_status(b.id) == "SUCCEEDED"
    assert reopened.replay(b.id, b.generation) == final.events
    assert len(reopened.replay(b.id, b.generation, final.events[-2].id)) == 1


def test_running_job_restart_records_failure_and_releases_commitments(tmp_path):
    url = f"sqlite:///{tmp_path}/interrupted.sqlite"
    first = BlocStore(url)
    b = make_bloc("running", "Headphones", Decimal("200"))
    add_member(b, "you", "150")
    first.create(b)
    transition(b, "NEGOTIATING")
    first.save(b, queue=True)
    assert first.claim_job(b.id)
    assert not first.claim_job(b.id)
    reopened = BlocStore(url)
    Runtime(reopened).recover()
    assert reopened.get(b.id).status == "FAILED"
    assert reopened.get(b.id).members[0].status == "RELEASED"
    assert reopened.job_status(b.id) == "FAILED"


def test_deadline_locks_joining_and_auto_starts_on_tick(tmp_path, monkeypatch):
    import time

    import pytest

    store = BlocStore(f"sqlite:///{tmp_path}/deadline.sqlite")
    b = make_bloc("due", "Headphones", Decimal("200"))
    add_member(b, "you", "150")
    b.closes_at = int(time.time()) - 1
    store.create(b)
    with pytest.raises(ValueError):
        add_member(b, "late", "150")
    runtime = Runtime(store, delay=0)

    async def run():
        await runtime.tick()
        await asyncio.gather(*runtime.tasks.values())

    asyncio.run(run())
    assert store.get(b.id).status == "SETTLED"


def test_scan_bonus_only_for_matching_open_unexpired_bloc(monkeypatch):
    import time

    monkeypatch.setattr(settings, "scan_mode", "fixture")
    b = make_bloc("match", "Aurora Q5 Black", Decimal("200"))
    b.product_key = "aurora-q5-black"  # the sample screenshot's (made-up) product
    storage.get_store().create(b)
    case = json.loads((ROOT / "evals/fixtures.json").read_text())[0]
    data = (ROOT / "evals" / case["file"]).read_bytes()
    with TestClient(app) as client:
        result = client.post("/scan", content=data, headers={"content-type": "image/png"}).json()
        assert result["score"]["bloc_bonus"] == 15 and result["score"]["value"] == 60
        assert result["recommendation"]["primary"] == "JOIN_BLOC"
        assert result["open_bloc_id"] == "match"
        b.closes_at = int(time.time()) - 1
        storage.get_store().save(b)
        result = client.post("/scan", content=data, headers={"content-type": "image/png"}).json()
        assert result["score"]["bloc_bonus"] == 0 and result["open_bloc_id"] is None


def test_queued_job_mode_change_fails_without_fixture_substitution(tmp_path):
    store = BlocStore(f"sqlite:///{tmp_path}/mode.sqlite")
    b = make_bloc("live-job", "Headphones", Decimal("200"), mode="live")
    add_member(b, "you", "150")
    store.create(b)
    transition(b, "NEGOTIATING")
    store.save(b, queue=True)
    asyncio.run(Runtime(store, mode="fixture").tick())
    assert store.get(b.id).status == "FAILED"
    assert store.get(b.id).members[0].status == "RELEASED"
    assert store.job_status(b.id) == "FAILED"


def test_history_and_retail_cache_have_distinct_keys():
    from maxx.flow import price_cache_key
    from maxx.scan import Item

    item = Item(title="Sony WH-1000XM5 Black", price="200")
    assert price_cache_key(item) != price_cache_key(item, history=True)


def test_orphaned_running_job_releases_after_dispatcher_recovers(tmp_path):
    store = BlocStore(f"sqlite:///{tmp_path}/orphan.sqlite")
    b = make_bloc("orphan", "Headphones", Decimal("200"))
    add_member(b, "you", "150")
    store.create(b)
    transition(b, "NEGOTIATING")
    store.save(b, queue=True)
    assert store.claim_job(b.id)
    asyncio.run(Runtime(store).tick())
    assert store.get(b.id).status == "FAILED"
    assert store.get(b.id).members[0].status == "RELEASED"
    assert store.job_status(b.id) == "FAILED"
