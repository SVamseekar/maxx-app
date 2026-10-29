"""Server-only provider transport. Logs metadata, never prompts, images or keys."""

import json
import time

import httpx2 as httpx

from maxx import storage
from maxx.config import settings
from maxx.costs import calculate_cost, worst_case_usd
from maxx.guardrails import ROLES, data_message, strip_reasoning, system_message, wire_schema


class ProviderError(Exception):
    pass


class ModelOutputError(ProviderError):
    """The model answered, but not within its contract, even after the one allowed retry."""


class BudgetExceeded(ProviderError):
    """A spending limit would be crossed, so the call was never made."""


class Rejected(Exception):  # noqa: N818 - a signal, not an error the caller handles
    def __init__(self, rule: str):
        self.rule = rule


def token_counts(usage):
    if not isinstance(usage, dict):
        return None
    allowed = {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
    }
    return {k: v for k, v in usage.items() if k in allowed and type(v) is int and v >= 0} or None


def log_call(record: dict):
    allowed = {
        "request_id",
        "provider",
        "purpose",
        "model",
        "status",
        "tokens",
        "cost_usd",
        "cost_status",
        "rate_date",
        "latency_ms",
        "guard",
    }
    value = {k: v for k, v in record.items() if k in allowed}
    value["tokens"] = token_counts(value.get("tokens"))
    storage.get_store().log_call(value)


def log_guard(request_id, role: str, rules: list[str]):
    """Record that a plain-code check changed or refused a model's answer. Rule names only."""
    if rules:
        log_call(
            {
                "request_id": request_id,
                "provider": "guard",
                "purpose": role,
                "status": "flagged",
                "guard": sorted(set(rules)),
                "latency_ms": 0,
            }
        )


def model_rates() -> dict:
    try:
        rates = json.loads(settings.model_rates_json)
    except ValueError:
        return {}
    return rates if isinstance(rates, dict) else {}


def reserve_for(request_id, provider, purpose, payload, record):
    """Hold the call's worst case before it is made, or refuse it. Listing models is free."""
    from maxx import budget

    if purpose == "models" or payload is None:
        return None
    try:
        if provider == "tavily":
            urls = len(payload.get("urls", [])) if purpose == "extract" else 0
            # Search: 1 credit (basic) or 2 (advanced). Extract: per 5 pages, 1 credit (basic) or
            # 2 (advanced); only pages that succeed are billed, so this is the worst case.
            advanced = (
                2
                if "advanced" in (payload.get("search_depth"), payload.get("extract_depth"))
                else 1
            )
            return budget.reserve_credits(request_id, (-(-urls // 5) if urls else 1) * advanced)
        text = json.dumps(payload.get("messages") or payload.get("input") or [])
        tools = json.dumps(payload.get("tools", []))
        images = text.count('"image_url"')
        # An image is counted by the model's per-image tokens, not by its base64 length.
        chars = len(text) + len(tools) - sum(len(part) for part in image_parts(payload))
        worst = worst_case_usd(
            payload.get("model"), chars, images, payload.get("max_tokens", 0), model_rates()
        )
        if worst is None:
            raise BudgetExceeded(
                "Live AI is paused: no price is configured for this model, so it is never "
                "called. Set MODEL_RATES_JSON."
            )
        return budget.reserve(request_id, purpose, worst)
    except BudgetExceeded:
        record["status"] = "refused"
        record["latency_ms"] = 0
        log_call(record)
        raise


def image_parts(payload) -> list[str]:
    return [
        part["image_url"]["url"]
        for message in payload.get("messages") or []
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]


async def request(client, request_id, calls, provider, purpose, url, payload=None, parse=None):
    start = time.perf_counter()
    record = {
        "request_id": request_id,
        "provider": provider,
        "purpose": purpose,
        "model": payload.get("model") if payload else None,
        "status": "error",
        "tokens": None,
        "cost_usd": None,
    }
    key = settings.nebius_api_key if provider == "nebius" else settings.tavily_api_key
    hold = reserve_for(request_id, provider, purpose, payload, record)
    try:
        response = await client.request(
            "POST" if payload is not None else "GET",
            url,
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderError(f"{provider} returned an invalid response. Retry the scan.")
        if purpose == "models" and (
            not isinstance(data.get("data"), list)
            or any(
                not isinstance(m, dict) or not isinstance(m.get("id"), str) for m in data["data"]
            )
        ):
            raise ProviderError("Nebius returned an invalid model list. Retry verification.")
        record["tokens"] = token_counts(data.get("usage"))
        if parse is not None:
            try:
                data = parse(data)
            except Rejected as exc:
                # Only the rule's name is kept; the reply itself is never logged.
                record["status"], record["guard"] = "rejected", [exc.rule]
                raise
        record["status"] = "ok"
        return data
    except httpx.TimeoutException as exc:
        record["status"] = "timeout"
        raise ProviderError(f"{provider} timed out. Try again.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(
            f"{provider} request failed. Check server configuration or retry."
        ) from exc
    finally:
        record["latency_ms"] = round((time.perf_counter() - start) * 1000)
        rates = model_rates()
        cost = calculate_cost(
            record["model"], record["tokens"], rates, embedding=purpose == "embed"
        )
        if hold is not None:
            from maxx import budget

            # Tavily costs a fixed number of credits; a model call costs what its usage says.
            budget.settle(hold, None if provider == "tavily" else cost)
        record["cost_usd"] = str(cost) if cost is not None else None
        record["cost_status"] = "estimated" if cost is not None else "unmeasured"
        record["rate_date"] = (
            rates.get(record["model"], {}).get("effective_date") if cost is not None else None
        )
        calls.append(record)
        log_call(record)


def reasoning_options(model: str) -> dict:
    """Nemotron thinks by default and its thinking is billed as output inside max_tokens, so every
    call asks for it off. Other models get no unknown options."""
    if model.startswith("nvidia/"):
        return {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"}
    return {}


async def chat(client, request_id, calls, role, data, schema, image_url=None, label="data"):
    """One call for one role: the role's rules and schema as the system message, `data` as one
    labelled JSON object, and a reply that must be exactly one object matching `schema`. The schema
    also goes in `response_format`, as Nebius advises. One retry on a reply out of contract; none
    on a cut-off reply, which would fail the same way."""
    spec = ROLES[role]
    wire = wire_schema(schema)
    model = getattr(settings, spec.setting)
    content = [{"type": "text", "text": data_message(label, data)}]
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    for attempt in range(2):

        def parse(reply, attempt=attempt):
            try:
                choice = reply["choices"][0]
                raw = choice["message"]["content"]  # never `reasoning` or `reasoning_content`
            except (KeyError, IndexError, TypeError):
                raise Rejected("no_content") from None
            if choice.get("finish_reason") == "length":
                raise Rejected("cut_off")
            try:
                return schema.model_validate_json(strip_reasoning(raw))
            except (ValueError, TypeError):
                raise Rejected("schema_failed" if attempt else "schema_retry") from None

        system = system_message(spec, wire, retry=bool(attempt))
        try:
            return await request(
                client,
                request_id,
                calls,
                "nebius",
                role,
                settings.nebius_base_url.rstrip("/") + "/chat/completions",
                {
                    "model": model,
                    "temperature": 0,
                    "max_tokens": spec.max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": schema.__name__, "schema": wire, "strict": True},
                    },
                    **reasoning_options(model),
                },
                parse,
            )
        except Rejected as exc:
            if attempt or exc.rule == "cut_off":
                raise ModelOutputError(
                    "The model returned unreadable data. Retry or use a clearer screenshot."
                ) from None
