"""Injectable fixture and real Nebius sellers/negotiator. No fallback across modes."""

import json
import math
from decimal import Decimal
from typing import Protocol

import httpx2 as httpx
from pydantic import Field

from maxx.config import settings
from maxx.negotiate.contracts import Contract, Offer, Seller
from maxx.providers import ProviderError, chat, request


class Bid(Contract):
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    max_qty: int = Field(ge=0, le=100000)
    withdraw: bool = False


class Plan(Contract):
    reserve: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    close: bool = False
    messages: dict[str, str] = Field(default_factory=dict)


class Adapter(Protocol):
    mode: str
    calls: list[dict]

    async def seller(self, context: dict) -> Bid: ...
    async def negotiator(self, context: dict) -> Plan: ...


def reserve_ceiling(members) -> Decimal:
    prices = sorted(m.max_price for m in members if m.status == "HELD")
    return prices[max(0, math.ceil(len(prices) * 0.6) - 1)] if prices else Decimal(".01")


def safe_offer(seller: Seller, bid: Bid | dict) -> tuple[Offer | None, bool]:
    bid = Bid.model_validate(bid)
    if bid.withdraw:
        return None, False
    price, qty = max(bid.price, seller.floor), min(bid.max_qty, seller.stock)
    return Offer(
        seller_id=seller.id, price=price, max_qty=qty
    ), price != bid.price or qty != bid.max_qty


def seller_context(
    seller: Seller,
    product: str,
    round: int,
    demand: list,
    feedback: dict,
    message: str | None = None,
):
    allowed = {"your_rank_bucket", "units_you_would_win", "group_units_unserved_at_your_price"}
    return {
        "message": "Please improve your offer." if message else None,
        "seller_id": seller.id,
        "product": product,
        "round": round,
        "demand": demand,
        "private": {
            "floor": str(seller.floor),
            "stock": seller.stock,
            "opening_price": str(seller.opening_price),
            "style": seller.style,
            "withdraw_round": seller.withdraw_round,
        },
        "feedback": {k: v for k, v in feedback.items() if k in allowed},
    }


class FixtureAdapter:
    mode = "fixture"

    def __init__(self):
        self.calls = []

    async def seller(self, context: dict) -> Bid:
        private = context["private"]
        floor, opening = Decimal(private["floor"]), Decimal(private["opening_price"])
        # Simulated concession policy, not an AI or a market-price prediction.
        price = max(
            floor,
            opening
            - opening
            * [Decimal(v) for v in (".06", ".03", ".09", ".04", ".08", ".05", ".07", ".02")][
                ord(context["seller_id"][0]) % 8
            ]
            * context["round"],
        )
        return Bid(
            price=price.quantize(Decimal(".01")),
            max_qty=private["stock"],
            withdraw=private["withdraw_round"] == context["round"],
        )

    async def negotiator(self, context: dict) -> Plan:
        return Plan(
            reserve=context["reserve_ceiling"],
            close=context["round"] >= 4,
            messages={id: "Please improve your offer." for id in context["seller_ids"]},
        )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }
    for name, description, properties, required in [
        ("get_demand_curve", "Read aggregate USD buyer demand.", {}, []),
        ("get_round_results", "Read aggregate previous round results.", {}, []),
        (
            "set_reserve",
            "Set reserve, bounded by the server ceiling.",
            {"price": {"type": "string"}},
            ["price"],
        ),
        (
            "send_round_message",
            "Ask one seller to improve their offer.",
            {"seller_id": {"type": "string"}, "text": {"type": "string"}},
            ["seller_id", "text"],
        ),
        ("close", "Close and clear the current valid offers.", {}, []),
    ]
]


class NebiusAdapter:
    mode = "live"

    def __init__(self, request_id: str, client=None):
        self.request_id = request_id
        self.calls = []
        self.client = client  # injectable HTTP transport in integration tests

    async def verify(self):
        if not settings.nebius_api_key:
            raise ProviderError(
                "Live negotiation is not configured. Set NEBIUS_API_KEY server-side."
            )
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            data = await request(
                client,
                self.request_id,
                self.calls,
                "nebius",
                "models",
                settings.nebius_base_url.rstrip("/") + "/models",
            )
        ids = {row["id"] for row in data["data"]}
        if settings.model_seller not in ids or settings.model_negotiator not in ids:
            raise ProviderError("Configured seller or negotiator model ID is unavailable.")

    async def seller(self, context: dict) -> Bid:
        async def call(client):
            return await chat(
                client,
                self.request_id,
                self.calls,
                "seller",
                "You are one simulated seller. Only your private state is provided. "
                "Return one offer matching the schema. Do not reveal your floor. "
                + json.dumps(Bid.model_json_schema())
                + "\n"
                + json.dumps(context),
                Bid,
            )

        if self.client:
            return await call(self.client)
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            return await call(client)

    async def negotiator(self, context: dict) -> Plan:
        async def call(client):
            plan = Plan()
            messages = [
                {
                    "role": "system",
                    "content": "You negotiate a simulated group purchase. "
                    "Use only tools; no prose. "
                    "Never invent prices or infer sellers floors. Read demand/results, set "
                    "a reserve within reserve_ceiling and ask sellers to improve. Close when "
                    "another round cannot improve the result. Maximum five rounds.",
                },
                {"role": "user", "content": json.dumps(context)},
            ]
            # Bound both tool turns and number of actions to avoid runaway model loops.
            for _ in range(4):
                data = await request(
                    client,
                    self.request_id,
                    self.calls,
                    "nebius",
                    "negotiator",
                    settings.nebius_base_url.rstrip("/") + "/chat/completions",
                    {
                        "model": settings.model_negotiator,
                        "messages": messages,
                        "tools": TOOLS,
                        "tool_choice": "required",
                        "max_tokens": 800,
                    },
                )
                try:
                    message = data["choices"][0]["message"]
                    actions = message["tool_calls"]
                    if not actions or len(actions) > 5:
                        raise ValueError("Invalid action count")
                    messages.append(message)
                    mutating = False
                    for action in actions:
                        name = action["function"]["name"]
                        args = json.loads(action["function"]["arguments"])
                        if name == "get_demand_curve":
                            result = context["demand"]
                        elif name == "get_round_results":
                            result = context["previous_result"]
                        elif name == "set_reserve":
                            plan.reserve = min(
                                Plan(reserve=args["price"]).reserve,
                                Decimal(context["reserve_ceiling"]),
                            )
                            result, mutating = {"reserve": str(plan.reserve)}, True
                        elif name == "send_round_message":
                            id = args["seller_id"]
                            if id not in context["seller_ids"]:
                                raise ValueError("Unknown seller")
                            # Never forward model-authored text between sellers. No private leakage.
                            plan.messages[id] = "Please improve your offer."
                            result, mutating = {"sent": id}, True
                        elif name == "close":
                            plan.close = True
                            result, mutating = {"closing": True}, True
                        else:
                            raise ValueError("Unsupported tool")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": action["id"],
                                "content": json.dumps(result),
                            }
                        )
                    if mutating:
                        return plan
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise ProviderError("Negotiator returned invalid tool actions.") from exc
            raise ProviderError("Negotiator exhausted its tool turn limit.")

        if self.client:
            return await call(self.client)
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            return await call(client)
