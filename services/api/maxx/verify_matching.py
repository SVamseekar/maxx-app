"""Authenticated embedding probe; external support remains unverified until this passes."""

import asyncio
import json

from maxx.matching import NebiusMatcher
from maxx.providers import ProviderError
from maxx.scan import Item


async def main():
    try:
        result = await NebiusMatcher().match(Item(title="Sony WH-1000XM5 Black"))
        print(json.dumps({"status": "verified", "mode": result.mode, "calls": result.calls}))
    except ProviderError:
        print(
            json.dumps(
                {
                    "status": "unverified",
                    "message": "Check server-side NEBIUS_API_KEY and MODEL_EMBED.",
                }
            )
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    asyncio.run(main())
