"""Priced, capped live check of the AI guardrails. Never prints keys, prompts or model content.

    python -m maxx.verify_guardrails            # print the planned calls and their worst case
    python -m maxx.verify_guardrails --run --yes  # make them, under AI_VERIFY_BUDGET_USD

It answers what the mocked tests cannot: which thinking switch Token Factory honours for each
Nemotron model, whether reasoning reaches `content` or eats `max_tokens`, whether Ultra still
calls tools with thinking off, how Gemma 3 and Nemotron 3.5 Super VL read the fixture
screenshots, and what one scan and one negotiation round cost.
"""

import argparse
import asyncio
import base64
import json
import time
import uuid
from decimal import Decimal

import httpx2 as httpx

from maxx import budget
from maxx.config import ROOT, settings
from maxx.costs import worst_case_usd
from maxx.providers import ProviderError, chat, model_rates, request
from maxx.scan import VisionItem

SUPER_VL = "nvidia/Nemotron-3.5-Super-VL"
GEMMA = "google/gemma-3-27b-it"  # the non-Nemotron vision baseline
PROBE = 'Return exactly {"ok": true} and nothing else.'
PROBE_TOKENS = 256  # room to see reasoning appear, small enough to cost under a tenth of a cent
VARIANTS = {
    "none": {},
    "chat_template_kwargs": {"chat_template_kwargs": {"enable_thinking": False}},
    "reasoning_effort": {"reasoning_effort": "none"},
    "both": {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"},
}


def _fixtures():
    return json.loads((ROOT / "evals/fixtures.json").read_text())


def _cost(model, chars, images, max_tokens, calls=1) -> Decimal:
    worst = worst_case_usd(model, chars, images, max_tokens, model_rates())
    if worst is None:
        raise SystemExit(f"No rate for {model}; set MODEL_RATES_JSON first.")
    return worst * calls


def vision_models() -> list[str]:
    return list(dict.fromkeys((settings.model_vision, SUPER_VL, GEMMA)))


def plan() -> list[dict]:
    """Every call the run may make, with its worst-case cost (retries included)."""
    steps = []
    nemotron = sorted(
        {settings.model_fast, settings.model_reason, settings.model_negotiator, SUPER_VL}
    )
    for model in nemotron:
        for variant in VARIANTS:
            steps.append(
                {
                    "check": "reasoning switch",
                    "model": model,
                    "variant": variant,
                    "calls": 1,
                    "worst_usd": _cost(model, 300, 0, PROBE_TOKENS),
                }
            )
    steps.append(
        {
            "check": "reasoning switch",
            "model": GEMMA,
            "variant": "none",
            "calls": 1,
            "worst_usd": _cost(GEMMA, 300, 0, PROBE_TOKENS),
        }
    )
    cases = len(_fixtures())
    for model in vision_models():
        steps.append(
            {
                "check": "vision on fixture screenshots",
                "model": model,
                "calls": cases * 2,
                "worst_usd": _cost(model, 2500, 1, 1200, cases * 2),
            }
        )
    steps += [
        {
            "check": "negotiator tools with thinking off",
            "model": settings.model_negotiator,
            "calls": 8,
            "worst_usd": _cost(settings.model_negotiator, 4000, 0, 400, 8),
        },
        {
            "check": "seller bid",
            "model": settings.model_seller,
            "calls": 2,
            "worst_usd": _cost(settings.model_seller, 2500, 0, 150, 2),
        },
        {
            "check": "catalogue embedding",
            "model": settings.model_embed,
            "calls": 1,
            "worst_usd": _cost(settings.model_embed, 1600, 0, 0),
        },
        {
            "check": "one full live scan (plus up to 2 Tavily credits)",
            "model": settings.model_fast,
            "calls": 8,
            "worst_usd": _cost(settings.model_vision, 2500, 1, 1200, 2)
            + _cost(settings.model_fast, 1500, 0, 200, 2)
            + _cost(settings.model_fast, 115000, 0, 1600, 2)
            + _cost(settings.model_reason, 3000, 0, 300, 2),
        },
    ]
    for step in steps:
        step["worst_usd"] = str(step["worst_usd"].quantize(Decimal(".000001")))
    return steps


def _spent(calls) -> Decimal:
    return sum((Decimal(c["cost_usd"]) for c in calls if c.get("cost_usd")), Decimal(0))


async def _probe(client, model, variant, calls) -> dict:
    data = await request(
        client,
        "verify-probe",
        calls,
        "nebius",
        "probe",
        settings.nebius_base_url.rstrip("/") + "/chat/completions",
        {
            "model": model,
            "temperature": 0,
            "max_tokens": PROBE_TOKENS,
            "messages": [{"role": "system", "content": PROBE}, {"role": "user", "content": "go"}],
            "response_format": {"type": "json_object"},
            **VARIANTS[variant],
        },
    )
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    usage = data.get("usage") or {}
    return {
        "model": model,
        "variant": variant,
        "finish_reason": choice.get("finish_reason"),
        "content_is_bare_json": content.strip().startswith("{") and content.strip().endswith("}"),
        "think_tags_in_content": "<think>" in content or "</think>" in content,
        "content_chars": len(content),
        "reasoning_field": bool(message.get("reasoning") or message.get("reasoning_content")),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
    }


def _same(got, want) -> bool:
    # "799" and "799.00" are the same price.
    try:
        return Decimal(str(got)) == Decimal(str(want))
    except (ArithmeticError, ValueError):
        return str(got or "") == str(want or "")


async def _vision(client, model, calls) -> dict:
    original = settings.model_vision
    settings.model_vision = model
    matches = fields = 0
    cases = []
    try:
        for case in _fixtures():
            data = (ROOT / "evals" / case["file"]).read_bytes()
            started = time.perf_counter()
            try:
                item = await chat(
                    client,
                    "verify-vision",
                    calls,
                    "vision",
                    {"screenshot": "the attached image"},
                    VisionItem,
                    "data:image/png;base64," + base64.b64encode(data).decode(),
                )
                got = item.model_dump(mode="json")
            except ProviderError as exc:
                got = {"error": str(exc)}
            want = case["item"]
            checked = ["title", "brand", "price", "currency"]
            hit = sum(_same(got.get(k), want.get(k)) for k in checked)
            matches, fields = matches + hit, fields + len(checked)
            cases.append(
                {
                    "file": case["file"],
                    "fields_matched": f"{hit}/{len(checked)}",
                    "error": got.get("error"),
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "prompt_tokens": (calls[-1].get("tokens") or {}).get("prompt_tokens"),
                }
            )
    finally:
        settings.model_vision = original
    return {"model": model, "field_accuracy": f"{matches}/{fields}", "cases": cases}


async def run() -> dict:
    from maxx.flow import run_scan
    from maxx.matching import NebiusMatcher
    from maxx.negotiate.adapters import NebiusAdapter, seller_context
    from maxx.negotiate.contracts import Seller

    calls: list[dict] = []
    report: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
        catalog = await request(
            client,
            "verify",
            calls,
            "nebius",
            "models",
            settings.nebius_base_url.rstrip("/") + "/models",
        )
        ids = {m["id"] for m in catalog["data"]}
        wanted = {s["model"] for s in plan()}
        report["missing_models"] = sorted(wanted - ids)
        report["probes"] = [
            await _probe(client, s["model"], s["variant"], calls)
            for s in plan()
            if s["check"] == "reasoning switch" and s["model"] in ids
        ]
        report["vision"] = [
            await _vision(client, model, calls) for model in vision_models() if model in ids
        ]
        adapter = NebiusAdapter("verify-negotiation", client=client)
        seller = Seller(id="A", floor="120", opening_price="150", stock=2)
        bid = await adapter.seller(seller_context(seller, "Test headphones", 1, [("150", 2)], {}))
        plan_ = await adapter.negotiator(
            {
                "round": 1,
                "product": "Test headphones",
                "demand": [["130.00", 2], ["150.00", 1]],
                "reserve_ceiling": "130.00",
                "previous_result": {"served": 0, "unserved": 3},
                "seller_ids": ["A"],
            }
        )
        seller_cost = _spent([c for c in adapter.calls if c["purpose"] in {"seller"}])
        negotiator_cost = _spent([c for c in adapter.calls if c["purpose"] == "negotiator"])
        calls += adapter.calls
        report["negotiation"] = {
            "bid_valid": bid is not None,
            "negotiator_used_tools": not plan_.fallback,
            "round_cost_usd": str(seller_cost * 8 + negotiator_cost),
            "five_round_estimate_usd": str((seller_cost * 8 + negotiator_cost) * 5),
        }
        match = await NebiusMatcher(client).match(VisionItem(title="Sony WH-1000XM5 Black"))
        calls += match.calls
        report["embedding"] = {"mode": match.mode, "top": match.candidates[0].product_key}
    case = _fixtures()[0]
    # The scan step must reach the providers even when .env keeps the app on fixture replay.
    original = settings.scan_mode
    settings.scan_mode = "live"
    try:
        scan = await run_scan((ROOT / "evals" / case["file"]).read_bytes(), "image/png", False, "v")
    except ProviderError as exc:
        # A failed scan is a finding, not a reason to lose the report. Its spend is in the ledger.
        scan = None
        report["scan"] = {"file": case["file"], "error": str(exc)}
    finally:
        settings.scan_mode = original
    if scan is not None:
        calls += [c.model_dump(mode="json") for c in scan.calls]
        report["scan"] = {
            "file": case["file"],
            "warnings": scan.warnings,
            "rows": len(scan.rows),
            "recommendation": scan.recommendation.primary,
            "cost_usd": str(_spent([c.model_dump(mode="json") for c in scan.calls])),
        }
    report["measured_total_usd"] = str(_spent(calls))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="make the live calls")
    parser.add_argument("--yes", action="store_true", help="confirm spending real credit")
    args = parser.parse_args(argv)
    steps = plan()
    worst = sum(Decimal(s["worst_usd"]) for s in steps)
    print(json.dumps({"planned": steps, "worst_case_total_usd": str(worst)}, indent=2))
    if not args.run:
        return
    if not args.yes:
        print("Live calls spend real credit. Re-run with --run --yes after reviewing the plan.")
        raise SystemExit(2)
    if not settings.nebius_api_key:
        print("NEBIUS_API_KEY is not set on this machine.")
        raise SystemExit(2)
    payer = budget.Payer("system", "verify:" + uuid.uuid4().hex[:8])
    with budget.payer_scope(payer, 200):
        try:
            report = asyncio.run(run())
        except ProviderError as exc:
            print(json.dumps({"status": "stopped", "reason": str(exc)}))
            raise SystemExit(1) from None
    (ROOT / "evals/guardrails-live.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
