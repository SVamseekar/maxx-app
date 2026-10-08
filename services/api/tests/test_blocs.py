import pytest

from maxx.negotiate.blocs import add_member, leave_member, transition
from maxx.negotiate.contracts import Bloc
from maxx.negotiate.store import BlocStore, Conflict


def bloc():
    return Bloc(
        id="test",
        title="Headphones Black",
        product_key="headphones-black",
        typical_price="200",
        target_price="150",
    )


def test_state_machine_join_leave_and_commitment_conservation():
    b = bloc()
    with pytest.raises(ValueError):
        add_member(b, "riya", "150")
    transition(b, "OPEN")
    m = add_member(b, "riya", "150")
    assert m.status == "HELD"
    assert b.events[-1].type == "member_joined"
    # Retried join is idempotent, changed price requires leave/rejoin.
    assert add_member(b, "riya", "150").id == m.id
    with pytest.raises(ValueError):
        add_member(b, "riya", "160")
    with pytest.raises(ValueError):
        add_member(b, "other", "201")
    leave_member(b, "riya")
    assert b.members[0].status == "LEFT"
    assert b.events[-1].type == "commitment_released"
    transition(b, "NEGOTIATING")
    with pytest.raises(ValueError):
        add_member(b, "other", "150")
    with pytest.raises(ValueError):
        transition(b, "OPEN")
    transition(b, "FAILED")
    with pytest.raises(ValueError):
        transition(b, "SETTLED")


def test_persistence_and_optimistic_conflict(tmp_path):
    url = f"sqlite:///{tmp_path}/blocs.sqlite"
    store = BlocStore(url)
    b = bloc()
    store.create(b)
    first, stale = store.get("test"), store.get("test")
    transition(first, "OPEN")
    store.save(first)
    transition(stale, "OPEN")
    with pytest.raises(Conflict):
        store.save(stale)
    assert BlocStore(url).get("test").status == "OPEN"
    assert store.get("test").revision == 1
    with pytest.raises(KeyError):
        store.get("missing")
