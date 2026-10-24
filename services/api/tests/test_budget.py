"""The AI budget ledger: worst-case holds before every paid call, settlement after, and caps that
hold under concurrency. Mocked transports only; nothing here reaches a provider."""

import asyncio
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx2 as httpx
import pytest

from maxx import budget, providers
from maxx.budget import Payer, payer_scope
from maxx.config import settings
from maxx.costs import worst_case_usd
from maxx.providers import BudgetExceeded

DAY = datetime(2026, 11, 3, 12, tzinfo=UTC).timestamp()
ANON = Payer("anonymous", "ip-hash")
USER = Payer("user", "u1")


@pytest.fixture(autouse=True)
def caps(monkeypatch):
    for name, value in {
        "ai_budget_usd": "20",
        "ai_daily_budget_usd": "0.40",
        "ai_anonymous_daily_budget_usd": "0.08",
        "ai_address_daily_budget_usd": "0.02",
        "ai_user_daily_budget_usd": "0.05",
        "ai_premium_user_daily_budget_usd": "0.25",
        "ai_paused": False,
        "tavily_monthly_credits": 900,
        "tavily_daily_credits": 40,
    }.items():
        monkeypatch.setattr(settings, name, value)


def hold(payer, usd, now=DAY, max_calls=10):
    with payer_scope(payer, max_calls):
        return budget.reserve("r", "vision", Decimal(usd), now)


def test_worst_case_counts_input_images_and_every_output_token():
    rates = {
        "m": {
            "input_usd_per_million": "0.10",
            "output_usd_per_million": "0.30",
            "effective_date": "2026-10-20",
            "image_tokens": 256,
        }
    }
    # 3000 chars / 3 = 1000 tokens, plus 2 images x 256, at $0.10; 1200 output tokens at $0.30.
    expected = (Decimal(1512) * Decimal("0.10") + Decimal(1200) * Decimal("0.30")) / 10**6
    assert worst_case_usd("m", 3000, 2, 1200, rates) == expected
    assert worst_case_usd("unknown", 3000, 0, 100, rates) is None
    assert worst_case_usd("m", 10, 0, 0, {"m": {"input_usd_per_million": "1"}}) is None


@pytest.mark.parametrize(
    "payer,usd,message",
    [
        (ANON, "0.03", "visitors"),
        (USER, "0.06", "your AI allowance for today"),
        (Payer("system", "negotiation"), "0.41", "today's AI budget is used up"),
    ],
)
def test_each_cap_refuses_with_its_own_clear_message(payer, usd, message):
    with pytest.raises(BudgetExceeded) as refused:
        hold(payer, usd)
    assert str(refused.value).startswith("Live AI is paused:")
    assert message in str(refused.value)


def test_anonymous_pool_is_shared_and_address_cap_is_per_address():
    for i in range(4):
        hold(Payer("anonymous", f"ip{i}"), "0.02")
    with pytest.raises(BudgetExceeded, match="visitors"):
        hold(Payer("anonymous", "ip9"), "0.01")
    hold(USER, "0.05")  # signed-in people keep the rest of the day


def test_premium_users_get_the_premium_allowance():
    with pytest.raises(BudgetExceeded):
        hold(USER, "0.10")
    assert hold(Payer("user", "u2", premium=True), "0.10")


def test_the_total_budget_is_never_crossed(monkeypatch):
    monkeypatch.setattr(settings, "ai_budget_usd", "0.05")
    hold(Payer("system", "s"), "0.04")
    with pytest.raises(BudgetExceeded, match="total AI budget"):
        hold(Payer("system", "s"), "0.02")


def test_a_refused_hold_leaves_no_partial_reservation():
    with pytest.raises(BudgetExceeded):
        hold(ANON, "0.03")  # passes total and day, fails the address cap
    assert budget.status(DAY)["day"]["reserved_usd"] == "0.000000"


def test_settling_replaces_the_hold_with_the_actual_cost():
    h = hold(USER, "0.04")
    budget.settle(h, Decimal("0.001"), DAY)
    day = budget.status(DAY)["day"]
    assert day["spent_usd"] == "0.001000" and day["reserved_usd"] == "0.000000"
    assert budget.remaining_for(USER, DAY) == Decimal("0.049")
    budget.settle(h, Decimal("0.001"), DAY)  # settling twice changes nothing
    assert budget.status(DAY)["day"]["spent_usd"] == "0.001000"


def test_missing_usage_settles_the_full_hold():
    h = hold(USER, "0.04")
    budget.settle(h, None, DAY)
    assert budget.status(DAY)["day"]["spent_usd"] == "0.040000"


def test_a_hold_that_is_never_settled_expires_as_spent():
    hold(USER, "0.04")
    budget.sweep(DAY + 3600)
    day = budget.status(DAY)["day"]
    assert day["spent_usd"] == "0.040000" and day["reserved_usd"] == "0.000000"


def test_settlement_after_midnight_goes_to_the_day_it_was_reserved_in():
    h = hold(USER, "0.04", DAY)
    budget.settle(h, Decimal("0.01"), DAY + 86400)
    assert budget.status(DAY)["day"]["spent_usd"] == "0.010000"
    assert budget.status(DAY + 86400)["day"]["spent_usd"] == "0.000000"


def test_each_request_has_a_call_cap():
    with payer_scope(USER, 2):
        budget.reserve("r", "vision", Decimal("0.001"), DAY)
        budget.reserve("r", "vision", Decimal("0.001"), DAY)
        with pytest.raises(BudgetExceeded, match="limit of 2 model calls"):
            budget.reserve("r", "vision", Decimal("0.001"), DAY)


def test_the_kill_switch_refuses_everything(monkeypatch):
    from maxx import audit

    audit.set_flag("ai_paused", "1")
    with pytest.raises(BudgetExceeded, match="switched it off"):
        hold(USER, "0.001")
    audit.set_flag("ai_paused", "0")
    monkeypatch.setattr(settings, "ai_paused", True)
    with pytest.raises(BudgetExceeded, match="switched it off"):
        hold(USER, "0.001")


def test_tavily_credits_have_daily_and_monthly_caps(monkeypatch):
    with payer_scope(USER, 100):
        for _ in range(40):
            budget.reserve_credits("r", 1, DAY)
        with pytest.raises(BudgetExceeded, match="web search"):
            budget.reserve_credits("r", 1, DAY)
    monkeypatch.setattr(settings, "tavily_monthly_credits", 40)
    with payer_scope(USER, 100), pytest.raises(BudgetExceeded, match="this month"):
        budget.reserve_credits("r", 1, DAY + 86400)


def race(cap_usd, amount_usd, now=DAY):
    """Two threads reserve at the same instant; return how many holds succeeded."""
    barrier = threading.Barrier(2)
    results = []

    def worker():
        with payer_scope(Payer("system", "race"), 10):
            barrier.wait()
            try:
                budget.reserve(str(uuid.uuid4()), "vision", Decimal(amount_usd), now)
                results.append("ok")
            except BudgetExceeded:
                results.append("refused")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_two_concurrent_requests_near_the_cap_cannot_both_pass(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", "0.10")
    assert sorted(race("0.10", "0.06")) == ["ok", "refused"]
    day = budget.status(DAY)["day"]
    assert Decimal(day["reserved_usd"]) + Decimal(day["spent_usd"]) <= Decimal("0.10")


@pytest.mark.skipif(
    not os.environ.get("MAXX_TEST_POSTGRES_URL"),
    reason="set MAXX_TEST_POSTGRES_URL to an admin URL of a local Postgres (make db-native)",
)
def test_two_concurrent_requests_near_the_cap_on_postgres(monkeypatch):
    from sqlalchemy import create_engine, text

    from maxx import storage
    from maxx.negotiate.store import BlocStore

    admin_url = os.environ["MAXX_TEST_POSTGRES_URL"]
    name = "maxx_budget_" + uuid.uuid4().hex[:8]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as db:
        db.execute(text(f"CREATE DATABASE {name}"))
    try:
        store = BlocStore(admin_url.rsplit("/", 1)[0] + "/" + name)
        monkeypatch.setattr(storage, "get_store", lambda: store)
        monkeypatch.setattr(settings, "ai_daily_budget_usd", "0.10")
        monkeypatch.setattr(settings, "ai_budget_usd", "100")
        for i in range(10):  # a fresh day each time, so every race starts from an empty cap
            assert sorted(race("0.10", "0.06", DAY + i * 86400)) == ["ok", "refused"]
            day = budget.status(DAY + i * 86400)["day"]
            assert Decimal(day["reserved_usd"]) + Decimal(day["spent_usd"]) <= Decimal("0.10")
        store.engine.dispose()
    finally:
        with admin.connect() as db:
            db.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


def call_nebius(monkeypatch, usage, model="nvidia/nemotron-3-super-120b-a12b"):
    sent = []

    def transport(req):
        sent.append(json.loads(req.content))
        body = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        if usage:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            with payer_scope(USER, 10):
                return await providers.request(
                    client,
                    "r",
                    [],
                    "nebius",
                    "verdict",
                    "https://nebius.test/v1/chat/completions",
                    {"model": model, "max_tokens": 300, "messages": [{"role": "user"}]},
                )

    return asyncio.run(go()), sent


def test_a_model_without_a_price_is_refused_before_any_request(monkeypatch):
    with pytest.raises(BudgetExceeded, match="no price"):
        call_nebius(monkeypatch, None, model="vendor/unpriced")
    assert budget.status()["day"]["spent_usd"] == "0.000000"


def test_a_live_call_is_settled_at_its_measured_cost(monkeypatch):
    call_nebius(monkeypatch, {"prompt_tokens": 1000, "completion_tokens": 100})
    # 1000 x $0.30 + 100 x $0.90 per million.
    assert budget.status()["day"]["spent_usd"] == "0.000390"
    assert budget.status()["day"]["reserved_usd"] == "0.000000"


def test_a_live_call_without_usage_is_charged_its_worst_case(monkeypatch):
    call_nebius(monkeypatch, None)
    assert Decimal(budget.status()["day"]["spent_usd"]) > Decimal("0.00027")


def test_the_model_list_is_free_and_never_held():
    async def go():
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": []}))
        async with httpx.AsyncClient(transport=transport) as client:
            await providers.request(client, "r", [], "nebius", "models", "https://n.test/models")

    asyncio.run(go())
    assert budget.status()["day"]["reserved_usd"] == "0.000000"
