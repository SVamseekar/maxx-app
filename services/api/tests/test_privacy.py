import asyncio
import json
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from maxx.negotiate.adapters import FixtureAdapter, seller_context
from maxx.negotiate.blocs import add_member, make_bloc, transition
from maxx.negotiate.runner import run_negotiation
from maxx.negotiate.store import BlocStore


@settings(max_examples=200, deadline=None, derandomize=True)
@given(st.lists(st.integers(1, 50000), min_size=8, max_size=8))
def test_private_seller_contexts_isolate_other_sellers(floors):
    bloc = make_bloc("private", "Headphones", Decimal("200"))
    for seller, floor in zip(bloc.sellers, floors, strict=True):
        seller.floor = Decimal(floor) / 100
        seller.style = "SECRET_PERSONA_" + seller.id
    for seller in bloc.sellers:
        context = seller_context(
            seller,
            bloc.title,
            1,
            [("200", 2)],
            {"floor": "OTHER_SECRET", "offers": floors, "your_rank_bucket": "cheapest"},
            "SECRET_MESSAGE",
        )
        assert context["private"]["floor"] == str(seller.floor)
        assert context["feedback"] == {"your_rank_bucket": "cheapest"}
        for other in bloc.sellers:
            if other.id != seller.id:
                assert other.style not in json.dumps(context)
        assert context["message"] == "Please improve your offer."


def test_runner_never_passes_private_seller_state_to_buyer_negotiator(tmp_path):
    class Spy(FixtureAdapter):
        async def negotiator(self, context):
            assert set(context) == {
                "round",
                "product",
                "demand",
                "reserve_ceiling",
                "previous_result",
                "seller_ids",
            }
            assert not any(
                k in json.dumps(context)
                for k in ("floor", "stock", "opening_price", "SECRET_PERSONA")
            )
            return await super().negotiator(context)

    store = BlocStore(f"sqlite:///{tmp_path}/privacy.sqlite")
    bloc = make_bloc("private", "Headphones", Decimal("200"))
    for s in bloc.sellers:
        s.style = "SECRET_PERSONA_" + s.id
    add_member(bloc, "you", "150")
    transition(bloc, "NEGOTIATING")
    store.create(bloc)
    asyncio.run(run_negotiation(store, bloc.id, Spy(), round_delay=0))
    result = store.get(bloc.id)
    assert result.status == "SETTLED"
    assert "SECRET_PERSONA" not in result.public().model_dump_json()
    assert '"floor"' not in result.public().model_dump_json()
