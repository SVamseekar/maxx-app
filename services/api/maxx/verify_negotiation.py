"""Live model/JSON/tool probe. Missing configuration exits nonzero; no fixture fallback."""

import asyncio
import json
import uuid

from maxx import budget
from maxx.negotiate.adapters import NebiusAdapter, safe_offer, seller_context
from maxx.negotiate.contracts import Seller
from maxx.providers import ProviderError


async def main():
    adapter = NebiusAdapter("verify-" + str(uuid.uuid4()))
    try:
        await adapter.verify()
        seller = Seller(id="A", floor="120", opening_price="150", stock=2)
        bid = await adapter.seller(
            seller_context(seller, "Test headphones black", 1, [("130.00", 2), ("150.00", 1)], {})
        )
        offer, clamped = safe_offer(seller, bid)
        plan = await adapter.negotiator(
            {
                "round": 1,
                "product": "Test headphones black",
                "demand": [("130.00", 2), ("150.00", 1)],
                "reserve_ceiling": "130.00",
                "previous_result": {"served": 0, "unserved": 3},
                "seller_ids": ["A"],
            }
        )
        print(
            json.dumps(
                {
                    "status": "verified",
                    "provider": "nebius",
                    "seller_json": True,
                    "negotiator_tools": True,
                    "offer": offer.model_dump(mode="json") if offer else None,
                    "clamped": clamped,
                    "plan": plan.model_dump(mode="json"),
                    "calls": adapter.calls,
                    "cost": "unmeasured",
                },
                indent=2,
            )
        )
    except ProviderError as exc:
        print(json.dumps({"status": "unverified", "message": str(exc), "calls": adapter.calls}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    # A verification run is the operator's own spend, capped like any request.
    with budget.payer_scope(budget.Payer("system", "verify"), 20):
        asyncio.run(main())
