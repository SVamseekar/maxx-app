import asyncio

import httpx2 as httpx
import pytest

from maxx.config import settings
from maxx.matching import NebiusMatcher
from maxx.providers import ProviderError
from maxx.scan import Item


def test_injected_embedding_transport_variant_rules_and_bad_dimensions(monkeypatch):
    monkeypatch.setattr(settings, "nebius_api_key", "test-only")

    def handler(request):
        import json

        body = json.loads(request.content)
        assert len(body["input"]) == 53
        return httpx.Response(
            200,
            json={
                "data": [{"index": i, "embedding": [1, 0]} for i in range(51)],
                "usage": {"total_tokens": 51},
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await NebiusMatcher(client).match(
                Item(title="Sony WH-1000XM5 Silver", variant="Silver")
            )
        assert result.mode == "live"
        assert result.candidates[0].product_key == "sony-wh1000xm5-silver"
        assert all(c.variant == "Silver" for c in result.candidates)
        assert result.calls[0]["tokens"]["total_tokens"] == 51
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
        ) as client:
            with pytest.raises(ProviderError):
                await NebiusMatcher(client).match(Item(title="Headphones"))

    asyncio.run(run())
