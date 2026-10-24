"""Injectable fixture and real Nebius sellers/negotiator. No fallback across modes."""

import json
import math
from decimal import Decimal
from typing import Protocol

import httpx2 as httpx
from pydantic import Field

from maxx.config import settings
from maxx.guardrails import ROLES, data_message, looks_like_instruction, system_message
from maxx.negotiate.contracts import Contract, Offer, Seller
from maxx.providers import ProviderError, chat, log_guard, reasoning_options, request

FIXED_MESSAGE = "Please improve your offer."


class Bid(Contract):
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    max_qty: int = Field(ge=0, le=100000)
    withdraw: bool = False


class Plan(Contract):
    reserve: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    close: bool = False
    messages: dict[str, str] = Field(default_factory=dict)
    fallback: bool = False  # the negotiator broke its contract; this is the fixed rule instead


class NoArgs(Contract):
    pass


class SetReserve(Contract):
    price: str = Field(pattern=r"^\d{1,9}(\.\d{1,2})?$")


class SendMessage(Contract):
    seller_id: str = Field(max_length=40)
    text: str = Field(max_length=500)  # required by the tool, never forwarded


TOOL_ARGS = {
    "get_demand_curve": NoArgs,
    "get_round_results": NoArgs,
    "set_reserve": SetReserve,
    "send_round_message": SendMessage,
    "close": NoArgs,
}


def fallback_plan(context: dict) -> Plan:
    """The fixed rule used when the negotiator model breaks its contract: the server's ceiling,
    the same fixed message to every seller, and a close at round four."""
    return Plan(
        reserve=context["reserve_ceiling"],
        close=context["round"] >= 4,
        messages={id: FIXED_MESSAGE for id in context["seller_ids"]},
        fallback=True,
    )


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
    # The floor is the hard limit, so it wins even over an opening price set below it.
    price = max(min(bid.price, seller.opening_price), seller.floor)
    qty = min(bid.max_qty, seller.stock)
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
    previous_price: Decimal | None = None,
):
    allowed = {"your_rank_bucket", "units_you_would_win", "group_units_unserved_at_your_price"}
    return {
        "message": FIXED_MESSAGE if message else None,
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
            "concession": str(seller.concession) if seller.concession is not None else None,
            "agent": seller.agent if seller.account_id else "persona",
            "guidance": clean_guidance(seller.guidance) if seller.account_id else "",
            "your_previous_price": str(previous_price) if previous_price is not None else None,
        },
        "feedback": {k: v for k, v in feedback.items() if k in allowed},
    }


def clean_guidance(text: str) -> str:
    """A seller's note to their own agent, as data: no control characters, bounded length. A note
    written as instructions to the model ("ignore your rules") is not passed on at all."""
    text = " ".join("".join(c if c.isprintable() else " " for c in text or "").split())[:280]
    return "" if looks_like_instruction(text) else text


def rules_bid(seller: Seller, round: int) -> Bid:
    """A real seller's fixed-concession agent: opening price less `concession` per round, never
    below the floor. Deterministic in every mode; no language model is involved."""
    rate = seller.concession or Decimal("0.05")
    price = max(seller.floor, seller.opening_price - seller.opening_price * rate * round)
    return Bid(price=price.quantize(Decimal(".01")), max_qty=seller.stock)


def guard_ai_bid(
    seller: Seller, bid: Bid | dict, previous: Decimal | None
) -> tuple[Offer | None, list[str]]:
    """The hard limits on a language-model seller agent, applied to every bid it makes.

    Whatever the model proposes: the price stays between the seller's floor and opening price,
    never rises above its own previous offer, falls by at most SELLER_AI_MAX_ROUND_DROP_PERCENT of
    the opening price per round, and the quantity never exceeds stock. Returns the offer and the
    names of the limits that had to be applied (shown in the room as a clamped offer).
    """
    bid = Bid.model_validate(bid)
    if bid.withdraw:
        return None, []
    applied: list[str] = []
    price = bid.price
    if price > seller.opening_price:
        price, _ = seller.opening_price, applied.append("opening")
    if previous is not None and price > previous:
        price, _ = previous, applied.append("no_increase")
    max_drop = seller.opening_price * Decimal(settings.seller_ai_max_round_drop_percent) / 100
    if previous is not None and previous - price > max_drop:
        price, _ = previous - max_drop, applied.append("max_drop")
    if price < seller.floor:
        price, _ = seller.floor, applied.append("floor")
    qty = min(bid.max_qty, seller.stock)
    if qty != bid.max_qty:
        applied.append("stock")
    return Offer(seller_id=seller.id, price=price.quantize(Decimal(".01")), max_qty=qty), applied


class FixtureAdapter:
    mode = "fixture"

    def __init__(self):
        self.calls = []

    async def seller(self, context: dict) -> Bid:
        private = context["private"]
        floor, opening = Decimal(private["floor"]), Decimal(private["opening_price"])
        if private.get("agent") == "ai":
            # Replay stand-in for a seller's AI agent (no model call in fixture mode): hold when
            # cheapest, concede harder when buyers it could serve are going unserved.
            feedback = context.get("feedback") or {}
            previous = Decimal(private["your_previous_price"] or opening)
            if feedback.get("your_rank_bucket") == "cheapest":
                rate = Decimal("0.01")
            elif feedback.get("group_units_unserved_at_your_price"):
                rate = Decimal("0.08")
            else:
                rate = Decimal("0.04")
            price = max(floor, previous - opening * rate)
            return Bid(price=price.quantize(Decimal(".01")), max_qty=private["stock"])
        # Simulated concession policy, not an AI or a market-price prediction.
        rates = [Decimal(v) for v in (".06", ".03", ".09", ".04", ".08", ".05", ".07", ".02")]
        rate = (
            Decimal(private["concession"])
            if private.get("concession")
            else rates[ord(context["seller_id"][0]) % 8]
        )
        price = max(floor, opening - opening * rate * context["round"])
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
        role = "seller_agent" if context["private"].get("agent") == "ai" else "seller"

        async def call(client):
            return await chat(
                client, self.request_id, self.calls, role, context, Bid, label="state"
            )

        if self.client:
            return await call(self.client)
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            return await call(client)

    async def negotiator(self, context: dict) -> Plan:
        """Up to four tool turns. Any turn outside the tool contract gets one fresh retry; a second
        bad attempt gives the fixed rule, so a confused model never ends the negotiation."""

        async def call(client):
            for _attempt in range(2):
                try:
                    return await self._negotiate(client, context)
                except InvalidTurn as exc:
                    log_guard(self.request_id, "negotiator", [exc.rule])
            return fallback_plan(context)

        if self.client:
            return await call(self.client)
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            return await call(client)

    async def _negotiate(self, client, context: dict) -> Plan:
        role = ROLES["negotiator"]
        plan = Plan()
        messages = [
            {"role": "system", "content": system_message(role)},
            {"role": "user", "content": data_message("room", context)},
        ]
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
                    "max_tokens": role.max_tokens,
                    **reasoning_options(settings.model_negotiator),
                },
            )
            try:
                message = data["choices"][0]["message"]
                actions = message.get("tool_calls")
            except (KeyError, IndexError, TypeError, AttributeError):
                raise InvalidTurn("no_tool_calls") from None
            if not isinstance(actions, list) or not actions:
                raise InvalidTurn("no_tool_calls")
            if len(actions) > 5:
                raise InvalidTurn("too_many_actions")
            # Only the tool calls go back into the conversation, never any text beside them.
            messages.append({"role": "assistant", "tool_calls": actions})
            mutating = False
            for action in actions:
                name, args = parse_action(action)
                if name == "get_demand_curve":
                    result = context["demand"]
                elif name == "get_round_results":
                    result = context["previous_result"]
                elif name == "set_reserve":
                    plan.reserve = min(
                        Plan(reserve=args.price).reserve, Decimal(context["reserve_ceiling"])
                    )
                    result, mutating = {"reserve": str(plan.reserve)}, True
                elif name == "send_round_message":
                    if args.seller_id not in context["seller_ids"]:
                        raise InvalidTurn("unknown_seller")
                    # Never forward model-authored text between sellers. No private leakage.
                    plan.messages[args.seller_id] = FIXED_MESSAGE
                    result, mutating = {"sent": args.seller_id}, True
                else:
                    plan.close = True
                    result, mutating = {"closing": True}, True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(action.get("id", ""))[:64],
                        "content": json.dumps(result),
                    }
                )
            if mutating:
                return plan
        raise InvalidTurn("turn_limit")


class InvalidTurn(Exception):  # noqa: N818 - a signal handled inside the adapter
    def __init__(self, rule: str):
        self.rule = rule


def parse_action(action) -> tuple[str, Contract]:
    """The tool name and its validated arguments, or InvalidTurn: unknown tools, arguments that
    are not a JSON object, and missing or extra arguments are all refused."""
    try:
        name = action["function"]["name"]
        args = json.loads(action["function"]["arguments"] or "{}")
    except (KeyError, TypeError, ValueError):
        raise InvalidTurn("malformed_action") from None
    if name not in TOOL_ARGS:
        raise InvalidTurn("unknown_tool")
    if not isinstance(args, dict):
        raise InvalidTurn("bad_arguments")
    try:
        return name, TOOL_ARGS[name].model_validate(args)
    except ValueError:
        raise InvalidTurn("bad_arguments") from None
