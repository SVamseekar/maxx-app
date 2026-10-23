"""Traffic behaviour: polling and listing must not re-read whole Blocs."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from maxx.main import app
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from tests.conftest import sign_up


@pytest.fixture
def runtime(tmp_path):
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def test_the_list_is_light_and_never_names_members(runtime):
    with TestClient(app) as client:
        rows = client.get("/blocs").json()
        full = client.get("/blocs/demo-success").json()
    assert {r["id"] for r in rows} >= {"demo-success", "demo-failure", "demo-flaky"}
    sample = next(r for r in rows if r["id"] == "demo-success")
    assert set(sample) == {
        "id",
        "title",
        "product_key",
        "status",
        "scenario",
        "mode",
        "target_price",
        "typical_price",
        "committed_total",
        "buyers",
        "closes_at",
        "viewer_is_owner",
        "viewer_joined",
    }
    assert sample["buyers"] == len([m for m in full["members"] if m["status"] != "LEFT"])
    assert len(str(rows)) < len(str(full)) / 20  # an order of magnitude smaller than one room


def test_an_unchanged_bloc_is_a_304_that_does_not_read_the_document(runtime):
    with TestClient(app) as client:
        first = client.get("/blocs/demo-success")
        etag = first.headers["etag"]
        reads = []

        @event.listens_for(runtime.store.engine, "before_cursor_execute")
        def spy(conn, cursor, statement, *rest):
            reads.append(statement)

        again = client.get("/blocs/demo-success", headers={"if-none-match": etag})
        event.remove(runtime.store.engine, "before_cursor_execute", spy)
    assert again.status_code == 304 and again.content == b""
    assert reads and all("bloc_documents.document" not in q for q in reads)


def test_the_tag_changes_with_the_viewer_and_the_revision(runtime):
    with TestClient(app) as anonymous, TestClient(app) as member:
        sign_up(member, "m@example.com")
        base = anonymous.get("/blocs/demo-success").headers["etag"]
        assert member.get("/blocs/demo-success").headers["etag"] != base
        member.post("/blocs/demo-success/join", json={"max_price": "150"})
        assert anonymous.get("/blocs/demo-success").headers["etag"] != base


def test_summaries_and_status_queries_never_parse_documents(runtime):
    statements = []

    @event.listens_for(runtime.store.engine, "before_cursor_execute")
    def spy(conn, cursor, statement, *rest):
        statements.append(statement)

    runtime.store.summaries()
    runtime.store.meta("demo-success")
    runtime.store.due_to_close(10**12)
    runtime.store.generations()
    event.remove(runtime.store.engine, "before_cursor_execute", spy)
    assert statements and all("bloc_documents.document" not in q for q in statements)


def test_viewer_flags_come_from_the_index_columns(runtime):
    with TestClient(app) as client:
        user = sign_up(client, "v@example.com")
        client.post("/blocs/demo-success/join", json={"max_price": "150"})
        rows = {r["id"]: r for r in client.get("/blocs").json()}
        assert rows["demo-success"]["viewer_joined"] is True
        assert rows["demo-failure"]["viewer_joined"] is False
        assert user["id"] not in str(rows)  # account ids never leak into the list


def test_streams_poll_cheaply_and_still_deliver_every_event(runtime):
    import asyncio

    from maxx.negotiate.stream import event_frames

    async def collect():
        frames = []
        async for frame in event_frames(runtime.store, "demo-failure", 0, interval=0.01):
            frames.append(frame)
            if len(frames) > 3:
                break
        return frames

    frames = asyncio.run(collect())
    assert frames[0].startswith("retry:") and any(f.startswith("id: ") for f in frames)
