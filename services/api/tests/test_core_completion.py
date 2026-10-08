import asyncio
from decimal import Decimal

from maxx.costs import calculate_cost
from maxx.market import target_price
from maxx.negotiate.adapters import FixtureAdapter, safe_offer, seller_context
from maxx.negotiate.blocs import add_member, leave_member, make_bloc
from maxx.scan import PriceRow, money_score


def rows():
    return [
        PriceRow(
            title="Headphones",
            url=f"https://shop{i}.example/item",
            price=p,
            shipping="0",
            same_item=True,
            in_stock=True,
        )
        for i, p in enumerate(["140", "160"])
    ]


def test_target_uses_trusted_delivered_median_not_private_floors():
    assert target_price(rows()) == Decimal("150.00")
    untrusted = rows()[0].model_copy(update={"shipping": None})
    assert target_price([untrusted]) is None


def test_bloc_bonus_requires_lower_open_target_and_clamps_score():
    assert money_score(Decimal("200"), rows(), False, Decimal("150")).bloc_bonus == 15
    assert money_score(Decimal("200"), rows(), False, Decimal("200")).bloc_bonus == 0
    assert money_score(Decimal("200"), rows(), True, Decimal("150")).value >= 0


def test_eight_personas_and_commitment_total():
    b = make_bloc("demo", "Headphones", Decimal("200"))
    assert len({s.style for s in b.sellers}) == 8
    add_member(b, "a", "150")
    add_member(b, "b", "160")
    assert b.public().committed_total == Decimal("310")
    leave_member(b, "a")
    assert b.public().committed_total == Decimal("160")
    assert b.closes_at > 0

    async def check():
        bids = []
        for seller in b.sellers:
            context = seller_context(seller, b.title, 1, [], {})
            bid = await FixtureAdapter().seller(context)
            offer, _ = safe_offer(seller, bid)
            bids.append(bid.price)
            assert offer.price >= seller.floor
            assert offer.max_qty <= seller.stock
        assert len(set(bids)) == 8

    asyncio.run(check())


def test_cost_is_decimal_and_unknown_rates_never_imply_free():
    rates = {
        "model": {
            "input_usd_per_million": "0.5",
            "output_usd_per_million": "2",
            "effective_date": "2026-10-05",
        }
    }
    assert calculate_cost(
        "model", {"prompt_tokens": 1000, "completion_tokens": 2000}, rates
    ) == Decimal("0.00450000")
    assert calculate_cost("unknown", {"prompt_tokens": 1000}, rates) is None
    assert calculate_cost("model", None, rates) is None


def test_bad_rates_and_missing_output_usage_stay_unmeasured():
    rates = {
        "model": {
            "input_usd_per_million": "NaN",
            "output_usd_per_million": "2",
            "effective_date": "2026-10-05",
        }
    }
    assert calculate_cost("model", {"prompt_tokens": 100, "completion_tokens": 1}, rates) is None
    rates["model"]["input_usd_per_million"] = "0.5"
    assert calculate_cost("model", {"total_tokens": 100}, rates) is None
    rates["model"]["effective_date"] = "not-a-date"
    assert calculate_cost("model", {"prompt_tokens": 100, "completion_tokens": 1}, rates) is None


def test_configured_cost_is_logged_from_transport_usage(monkeypatch):
    import json

    import httpx2 as httpx

    from maxx import storage
    from maxx.config import settings
    from maxx.providers import request

    rates = {
        "model": {
            "input_usd_per_million": "0.5",
            "output_usd_per_million": "2",
            "effective_date": "2026-10-05",
        }
    }
    monkeypatch.setattr(settings, "model_rates_json", json.dumps(rates))

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"usage": {"prompt_tokens": 1000, "completion_tokens": 2000}}
                )
            )
        ) as client:
            calls = []
            await request(
                client,
                "test",
                calls,
                "nebius",
                "seller",
                "https://nebius.example/chat",
                {"model": "model"},
            )
            assert calls[0]["cost_usd"] == "0.00450000"
            assert calls[0]["cost_status"] == "estimated"

    asyncio.run(run())
    assert storage.get_store().recent_calls()[0]["rate_date"] == "2026-10-05"
