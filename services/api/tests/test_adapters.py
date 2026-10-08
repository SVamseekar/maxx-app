import asyncio
import json
from decimal import Decimal

import httpx2 as httpx
import pytest

from maxx import providers
from maxx.negotiate.adapters import NebiusAdapter, Plan, seller_context
from maxx.negotiate.contracts import Seller


def test_real_adapter_http_contract_tools_and_privacy(monkeypatch, tmp_path):
    sent = []

    def transport(req):
        data = json.loads(req.content)
        sent.append(data)
        if "tools" in data:
            tool = {
                "id": "1",
                "type": "function",
                "function": {"name": "set_reserve", "arguments": '{"price":"999.00"}'},
            }
            message = {"role": "assistant", "tool_calls": [tool]}
        else:
            text = data["messages"][1]["content"][0]["text"]
            assert "PRIVATE-FLOOR-OTHER-SELLER" not in text
            assert "120.01" in text
            message = {"content": '{"price":"121.00","max_qty":2,"withdraw":false}'}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            adapter = NebiusAdapter("test", client=client)
            context = seller_context(
                Seller(id="A", floor="120.01", opening_price="150", stock=2),
                "headphones",
                1,
                [("150", 2)],
                {},
            )
            assert (await adapter.seller(context)).price == Decimal("121")
            plan = await adapter.negotiator(
                {"reserve_ceiling": "150", "demand": [], "previous_result": {}, "seller_ids": ["A"]}
            )
            assert plan.reserve == Decimal("150")
            assert len(adapter.calls) == 2

    asyncio.run(run())
    assert len(sent[1]["tools"]) == 5
    assert "floor" not in sent[1]["messages"][1]["content"]

    from maxx import storage

    audit = str(storage.get_store().recent_calls())
    assert "120.01" not in audit


def test_invalid_negotiator_tool_is_rejected(monkeypatch, tmp_path):

    def transport(req):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "1",
                                    "function": {"name": "set_price_above_max", "arguments": "{}"},
                                }
                            ]
                        }
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(providers.ProviderError):
                await NebiusAdapter("test", client=client).negotiator({})

    asyncio.run(run())


def test_runner_clamps_reserve_and_retries_recoverable_failure(tmp_path):
    from test_negotiation import setup_bloc

    from maxx.negotiate.adapters import FixtureAdapter
    from maxx.negotiate.runner import run_negotiation

    class RetryOnce(FixtureAdapter):
        failed = False

        async def negotiator(self, context):
            if not self.failed:
                self.failed = True
                raise TimeoutError()
            return Plan(reserve="99999", close=context["round"] == 2)

    store = setup_bloc(tmp_path)
    asyncio.run(run_negotiation(store, "test", RetryOnce(), round_delay=0))
    b = store.get("test")
    reserve = next(e for e in b.events if e.type == "reserve_set")
    assert Decimal(reserve.data["price"]) == Decimal("170")
    assert b.status == "SETTLED"
    assert sum(e.type == "provider_retry" for e in b.events) == 1
