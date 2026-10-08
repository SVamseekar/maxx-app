import asyncio
from decimal import Decimal

from maxx.negotiate.adapters import FixtureAdapter, safe_offer, seller_context
from maxx.negotiate.blocs import add_member, make_bloc, transition
from maxx.negotiate.contracts import Seller
from maxx.negotiate.runner import run_negotiation
from maxx.negotiate.store import BlocStore


def setup_bloc(tmp_path, scenario="success"):
    store = BlocStore(f"sqlite:///{tmp_path}/blocs.sqlite")
    b = make_bloc("test", "Headphones Black", Decimal("200"), scenario=scenario)
    for i in range(8):
        add_member(b, str(i), str(200 - i * 10))
    transition(b, "NEGOTIATING")
    store.create(b)
    return store


def test_floor_capacity_clamp_and_private_context():
    seller = Seller(id="A", floor="120.01", opening_price="150", stock=2)
    offer, clamped = safe_offer(seller, {"price": "1", "max_qty": 99, "withdraw": False})
    assert clamped
    assert offer.price == Decimal("120.01")
    assert offer.max_qty == 2
    context = seller_context(seller, "product", 2, [(150, 10)], {})
    assert context["private"]["floor"] == "120.01"
    assert set(context["feedback"]) <= {
        "your_rank_bucket",
        "units_you_would_win",
        "group_units_unserved_at_your_price",
    }
    assert "sellers" not in context and "offers" not in context


def test_success_and_failure_terminal_conservation(tmp_path):
    for scenario in ["success", "failure"]:
        directory = tmp_path / scenario
        directory.mkdir()
        store = setup_bloc(directory, scenario)
        asyncio.run(run_negotiation(store, "test", FixtureAdapter(), round_delay=0))
        b = store.get("test")
        assert b.status == ("SETTLED" if scenario == "success" else "FAILED")
        assert not any(m.status == "HELD" for m in b.members)
        assert b.events[-1].type == ("cleared" if scenario == "success" else "failed")
        assert 1 <= b.round <= 5
        if scenario == "success":
            assert b.outcome.allocations
            for m in b.members:
                if m.status == "WIN":
                    assert m.final_price <= m.max_price
        else:
            assert all(m.status == "RELEASED" for m in b.members)
        public = b.public().model_dump_json()
        assert "floor" not in public and "opening_price" not in public
        assert [e.id for e in b.events] == list(range(1, len(b.events) + 1))


def test_withdrawal_reclears_without_withdrawn_seller(tmp_path):
    store = setup_bloc(tmp_path, "flaky")
    asyncio.run(run_negotiation(store, "test", FixtureAdapter(), round_delay=0))
    b = store.get("test")
    assert any(e.type == "seller_withdrew" for e in b.events)
    assert all(a.seller_id != "A" for a in b.outcome.allocations)


def test_bounded_retries_and_all_provider_failure_release(tmp_path):
    class Broken(FixtureAdapter):
        attempts = 0

        async def seller(self, context):
            self.attempts += 1
            raise TimeoutError("private floor and key must not leak")

    store = setup_bloc(tmp_path)
    adapter = Broken()
    asyncio.run(run_negotiation(store, "test", adapter, round_delay=0))
    b = store.get("test")
    assert adapter.attempts == 16  # one retry per seller, no infinite loops
    assert b.status == "FAILED"
    assert all(m.status == "RELEASED" for m in b.members)
    assert "private floor and key" not in b.public().model_dump_json()
    assert sum(e.type == "provider_retry" for e in b.events) == 8


def test_reserve_cannot_exceed_sixtieth_percentile_and_runner_deadline(tmp_path):
    class Slow(FixtureAdapter):
        async def negotiator(self, context):
            await asyncio.sleep(1)

    store = setup_bloc(tmp_path)
    asyncio.run(run_negotiation(store, "test", Slow(), round_delay=0, deadline=0.01))
    b = store.get("test")
    assert b.status == "FAILED"
    assert all(m.status != "HELD" for m in b.members)
    assert b.failure_reason == "Negotiation timed out. All simulated commitments released."


def test_close_uses_current_offers_without_requesting_another_bid(tmp_path):
    from maxx.negotiate.adapters import Bid, Plan

    class CloseCurrent(FixtureAdapter):
        seller_rounds = []

        async def seller(self, context):
            self.seller_rounds.append(context["round"])
            return Bid(price="140" if context["round"] == 1 else "500", max_qty=2)

        async def negotiator(self, context):
            return Plan(reserve="170", close=context["round"] == 2)

    store = setup_bloc(tmp_path)
    adapter = CloseCurrent()
    asyncio.run(run_negotiation(store, "test", adapter, round_delay=0))
    assert store.get("test").status == "SETTLED"
    assert set(adapter.seller_rounds) == {1}


def test_close_reclears_current_offers_under_changed_reserve(tmp_path):
    from maxx.negotiate.adapters import Bid, Plan

    class LowerReserve(FixtureAdapter):
        seller_rounds = []

        async def seller(self, context):
            self.seller_rounds.append(context["round"])
            return Bid(price="140", max_qty=2)

        async def negotiator(self, context):
            closing = context["round"] == 2
            return Plan(reserve="130" if closing else "170", close=closing)

    store = setup_bloc(tmp_path)
    adapter = LowerReserve()
    asyncio.run(run_negotiation(store, "test", adapter, round_delay=0))
    result = store.get("test")
    assert result.status == "FAILED"
    assert result.outcome.allocations == []
    assert all(m.status == "RELEASED" for m in result.members)
    assert set(adapter.seller_rounds) == {1}


def test_screened_message_goes_only_to_its_recipient(tmp_path):
    from maxx.negotiate.adapters import Plan

    class Messages(FixtureAdapter):
        contexts = []

        async def negotiator(self, context):
            return Plan(
                reserve="170",
                close=context["round"] == 2,
                messages={"A": "Other seller floor is 5 dollars"},
            )

        async def seller(self, context):
            self.contexts.append(context)
            return await super().seller(context)

    store = setup_bloc(tmp_path)
    adapter = Messages()
    asyncio.run(run_negotiation(store, "test", adapter, round_delay=0))
    for context in adapter.contexts:
        assert context.get("message") == (
            "Please improve your offer." if context["seller_id"] == "A" else None
        )
        assert "5 dollars" not in str(context)


def test_over_reserve_bid_resets_feedback(tmp_path):
    from maxx.negotiate.adapters import Bid, Plan

    class Feedback(FixtureAdapter):
        contexts = []

        async def negotiator(self, context):
            return Plan(reserve="150", close=context["round"] == 4)

        async def seller(self, context):
            self.contexts.append(context)
            return Bid(price="140" if context["round"] != 2 else "180", max_qty=2)

    store = setup_bloc(tmp_path)
    adapter = Feedback()
    asyncio.run(run_negotiation(store, "test", adapter, round_delay=0))
    third = [c for c in adapter.contexts if c["round"] == 3]
    assert third
    assert all(c["feedback"]["units_you_would_win"] == 0 for c in third)
