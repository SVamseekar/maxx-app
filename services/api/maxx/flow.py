import base64
import hashlib
import json
import re
import time
from decimal import Decimal
from urllib.parse import urlparse

import httpx2 as httpx
from pydantic import Field

from maxx import storage
from maxx.config import ROOT, settings
from maxx.guardrails import has_link, looks_like_instruction
from maxx.matching import CATALOG, match_item
from maxx.providers import BudgetExceeded, ProviderError, chat, log_guard, request
from maxx.scan import (
    Contract,
    Identity,
    Item,
    Move,
    PriceRow,
    ScanResult,
    VisionItem,
    money_score,
    template_move,
)

SALES = re.compile(
    r"\b(?:subscribe|sign up|signup|newsletter|coupon|promo code|discount code|password|card "
    r"number|call us|email us|contact us|click|download|install|follow us|gift card)\b",
    re.I,
)
INJECTED_PAGE = "A page with text aimed at AI tools was left out of the score. Check it by hand."


class Rows(Contract):
    rows: list[PriceRow] = Field(max_length=8)


def visible_price(price: Decimal, text: str) -> bool:
    # Do not allow a model to manufacture a price absent from its evidence text.
    amounts = re.findall(r"(?:USD\s*|\$\s*)(\d[\d,]*(?:\.\d{1,2})?)(?!\d|\.\d)", text)
    return any(Decimal(value.replace(",", "")) == price for value in amounts)


def words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def grounded_identity(item: Item, identity: Identity) -> bool:
    """Every word the normaliser returns must already be on the screenshot."""
    seen = words(item.title) | words(item.visible_text)
    return all(words(value) <= seen for value in (identity.brand, identity.model, identity.variant))


def check_verdict(move: Move, expected: str, item: Item) -> str | None:
    """The first rule a model-written verdict breaks, or None. It may only explain the one move."""
    text = move.headline + " " + move.explanation
    if move.primary != expected:
        return "verdict_move"
    if re.search(r"\d|\$|%|percent", text, re.I):
        return "verdict_numbers"
    if has_link(text) or looks_like_instruction(text):
        return "verdict_link_or_instruction"
    if SALES.search(text):
        return "verdict_offer"
    known = words(" ".join(filter(None, [item.title, item.brand, item.model, item.merchant])))
    brands = {p.brand.casefold() for p in CATALOG}
    for sentence in re.split(r"[.!?]+\s*", text):
        for i, word in enumerate(re.findall(r"[A-Za-z][\w-]*", sentence)):
            if words(word) <= known:
                continue
            # Names must come from the input: a known brand anywhere, a capitalised word that
            # does not start a sentence, or a mixed-case product name such as "iPhone".
            name = i > 0 and word[0].isupper() or re.search(r"[a-z][A-Z]", word)
            if name or word.casefold() in brands:
                return "verdict_unknown_name"
    return None


def ground_rows(
    rows: list[PriceRow], sources: list[dict], fired: list[str] | None = None
) -> list[PriceRow]:
    fired = [] if fired is None else fired
    by_url = {s["url"]: s for s in sources}
    result = []
    seen_hosts = set()
    for row in rows:
        source = by_url.get(str(row.url))
        if not source:
            continue
        text = source["content"]
        host = urlparse(str(row.url)).hostname
        if host in seen_hosts or not visible_price(row.price, text):
            continue
        if row.evidence not in text or not row.evidence:
            continue
        if has_link(row.title) or looks_like_instruction(row.title + " " + row.evidence):
            fired.append("row_instruction")
            continue
        if looks_like_instruction(text):
            # The page talks to the model, so nothing it says about price or stock is trusted.
            fired.append("page_instruction")
            row.same_item = False
        # Explicitly reject non-retail condition and ungrounded shipping/stock claims.
        if re.search(
            r"\b(refurbished|renewed|used|out of stock|sold out|per month|"
            r"CAD|AUD|HKD|SGD|EUR|GBP)\b|[€£₹]",
            text,
            re.I,
        ):
            row.same_item = False
        if row.shipping == 0 and not re.search(r"free shipping|shipping\s*:?\s*\$0", text, re.I):
            row.shipping = None
        elif row.shipping and not re.search(
            rf"shipping\s*:?\s*\$\s*{re.escape(str(row.shipping))}", text, re.I
        ):
            row.shipping = None
        row.in_stock = row.in_stock and bool(
            re.search(r"\bin stock\b|available to ship", text, re.I)
        )
        seen_hosts.add(host)
        result.append(row)
    return result


def price_cache_key(item, history=False):
    matched = match_item(item)
    identity = {k: getattr(item, k) for k in ("title", "brand", "model", "variant")}
    if not matched.requires_confirmation:
        identity = {"product_key": matched.candidates[0].product_key}
    identity.update(
        qty=item.qty, currency=item.currency, purpose="history" if history else "retail"
    )
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def flag_outliers(rows: list[PriceRow], price: Decimal | None, warnings: list[str]) -> list[str]:
    """A new item at under half the scanned price is almost never the same offer."""
    fired = []
    for row in rows:
        if price and row.same_item and row.price < price / 2:
            row.same_item = False
            fired.append("price_outlier")
    if fired:
        warnings.append(
            "A listing far below your price looks too good to be true and was left out of the "
            "score. Check it by hand."
        )
    return fired


async def comparable_prices(client, item, request_id, calls, history=False, warnings=None):
    warnings = [] if warnings is None else warnings
    query = " ".join(filter(None, [item.brand, item.model, item.variant, item.title]))[:400] + (
        " USD price history deal buy new" if history else " USD price buy new"
    )
    cache_key = price_cache_key(item, history)
    cached = storage.get_store().cache_get(cache_key)
    if cached is not None:
        try:
            rows = [PriceRow.model_validate(r) for r in cached]
        except ValueError:
            rows = None  # written under older, looser limits: search again
        if rows is not None:
            calls.append(
                {"provider": "tavily", "purpose": "search", "status": "cache", "latency_ms": 0}
            )
            log_guard(request_id, "extract", flag_outliers(rows, item.price, warnings))
            return rows
    data = await request(
        client,
        request_id,
        calls,
        "tavily",
        "search",
        "https://api.tavily.com/search",
        {"query": query, "search_depth": "basic", "max_results": 8},
    )
    sources = [
        {"url": s["url"], "content": (s.get("title", "") + "\n" + s.get("content", ""))[:10000]}
        for s in data.get("results", [])
        if s.get("url", "").startswith("https://")
    ]
    missing = [s["url"] for s in sources if not re.search(r"\$\s*\d|USD\s*\d", s["content"])][:3]
    if missing:
        extracted = await request(
            client,
            request_id,
            calls,
            "tavily",
            "extract",
            "https://api.tavily.com/extract",
            {"urls": missing},
        )
        for source in sources:
            for row in extracted.get("results", []):
                if row.get("url") == source["url"]:
                    source["content"] += "\n" + row.get("raw_content", "")[:10000]
    if not sources:
        return []
    parsed = await chat(
        client,
        request_id,
        calls,
        "extract",
        {
            "item": item.model_dump(
                mode="json", include={"title", "brand", "model", "variant", "qty", "currency"}
            ),
            "sources": sources,
        },
        Rows,
    )
    fired = []
    rows = ground_rows(parsed.rows, sources, fired)
    if "page_instruction" in fired or "row_instruction" in fired:
        warnings.append(INJECTED_PAGE)
    storage.get_store().cache_put(cache_key, [r.model_dump(mode="json") for r in rows])
    log_guard(request_id, "extract", fired + flag_outliers(rows, item.price, warnings))
    return rows


async def run_scan(
    data: bytes, mime: str, owns: bool, request_id: str, corrections: dict | None = None
) -> ScanResult:
    started = time.perf_counter()
    calls = []
    warnings = []
    if settings.scan_mode == "fixture":
        manifest = json.loads((ROOT / "evals/fixtures.json").read_text())
        case = next((c for c in manifest if c["sha256"] == hashlib.sha256(data).hexdigest()), None)
        if case is None:
            raise ProviderError(
                "Fixture mode accepts only the supplied sample screenshots. Configure"
                " live mode for your own images."
            )
        item = Item.model_validate(case["item"])
        rows = [PriceRow.model_validate(r) for r in case["rows"]]
        warnings.append(
            "Fixture replay: extraction and prices are canned test data, not live provider results."
        )
    elif settings.scan_mode == "live":
        if not settings.nebius_api_key or not settings.tavily_api_key:
            raise ProviderError(
                "Live scanning is not configured. Follow docs/operator-actions.md to "
                "configure providers."
            )
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            catalog = await request(
                client,
                request_id,
                calls,
                "nebius",
                "models",
                settings.nebius_base_url.rstrip("/") + "/models",
            )
            ids = {m["id"] for m in catalog.get("data", [])}
            if any(
                m not in ids
                for m in [settings.model_vision, settings.model_fast, settings.model_reason]
            ):
                raise ProviderError(
                    "A configured model ID is unavailable. Run the provider verification "
                    "script and update MODEL_* on the server."
                )
            item = await chat(
                client,
                request_id,
                calls,
                "vision",
                {"screenshot": "the attached image"},
                VisionItem,
                "data:" + mime + ";base64," + base64.b64encode(data).decode(),
            )
            item = Item.model_validate(item.model_dump())
            if looks_like_instruction(item.visible_text):
                item.price = None
                log_guard(request_id, "vision", ["screenshot_instruction"])
                warnings.append(
                    "The screenshot contains text aimed at AI tools, so its price was not read "
                    "automatically. Enter the price to continue."
                )
            elif item.price is not None and not visible_price(item.price, item.visible_text):
                item.price = None
                log_guard(request_id, "vision", ["price_not_visible"])
                warnings.append("The extracted price lacked visible USD evidence and was removed.")
            try:
                normalised = await chat(
                    client,
                    request_id,
                    calls,
                    "normalise",
                    item.model_dump(
                        mode="json", include={"title", "brand", "model", "variant", "visible_text"}
                    ),
                    Identity,
                    label="item",
                )
            except BudgetExceeded as exc:
                normalised = None
                warnings.append(str(exc))
            except ProviderError:
                normalised = None
            if normalised is not None and grounded_identity(item, normalised):
                # A null means the model was unsure, so the screenshot's own value stays.
                item.brand = normalised.brand or item.brand
                item.model = normalised.model or item.model
                item.variant = normalised.variant or item.variant
            else:
                if normalised is not None:
                    log_guard(request_id, "normalise", ["identity_not_on_screenshot"])
                warnings.append(
                    "Kept the names read from the screenshot; the tidied names were not usable."
                )
            if corrections:
                item = item.model_copy(update=corrections)
            rows = []
            if item.title and item.price and item.currency == "USD":
                try:
                    rows = await comparable_prices(client, item, request_id, calls, False, warnings)
                except BudgetExceeded as exc:
                    warnings.append(str(exc))
                except ProviderError:
                    warnings.append(
                        "Price search failed. Try scanning again; no score was inferred."
                    )
            score = money_score(item.price, rows, owns)
            move = template_move(item, score)
            if not score.low_confidence and score.value is not None:
                try:
                    candidate = await chat(
                        client,
                        request_id,
                        calls,
                        "verdict",
                        {
                            "item": item.model_dump(mode="json"),
                            "score": score.model_dump(mode="json"),
                            "primary": move.primary,
                        },
                        Move,
                    )
                    broken = check_verdict(candidate, move.primary, item)
                    if broken is None:
                        move = candidate
                    else:
                        log_guard(request_id, "verdict", [broken])
                        warnings.append(
                            "The written verdict failed a safety check; using the deterministic "
                            "template."
                        )
                except BudgetExceeded as exc:
                    warnings.append(str(exc) + " Using the deterministic verdict.")
                except ProviderError:
                    warnings.append("Verdict model failed; using the deterministic template.")
            return finish(item, rows, owns, request_id, calls, warnings, started, move)
    else:
        raise ProviderError("SCAN_MODE must be live or fixture.")
    if corrections:
        if corrections.get("title", item.title) != item.title:
            rows = []
        item = item.model_copy(update=corrections)
    return finish(item, rows, owns, request_id, calls, warnings, started)


def finish(item, rows, owns, request_id, calls, warnings, started, move=None):
    matched = match_item(item)
    open_bloc = None
    if not matched.requires_confirmation and item.currency == "USD":
        key = matched.candidates[0].product_key
        candidates = [
            b
            for b in storage.get_store().list()
            if b.product_key == key
            and b.status == "OPEN"
            and b.closes_at > int(time.time())
            and b.target_price is not None
            and b.market_mode != "unavailable"
            and b.market_expires_at > int(time.time())
        ]
        open_bloc = min(candidates, key=lambda b: (b.target_price, b.id), default=None)
    score = money_score(
        item.price if item.currency == "USD" else None,
        rows,
        owns,
        open_bloc.target_price if open_bloc else None,
    )
    if score.bloc_bonus:
        move = template_move(item, score)
    if not item.title or not item.price:
        warnings.append(
            "Product or price could not be read. Edit the details or upload a clearer screenshot."
        )
    if item.currency != "USD":
        warnings.append("This milestone supports USD only; no currency conversion is inferred.")
    if score.low_confidence:
        warnings.append(
            "Fewer than two independent comparable listings with known shipping "
            "and stock. Low confidence."
        )
    return ScanResult(
        request_id=request_id,
        mode=settings.scan_mode,
        item=item,
        rows=rows,
        score=score,
        recommendation=move or template_move(item, score),
        warnings=warnings,
        latency_ms=round((time.perf_counter() - started) * 1000),
        calls=calls,
        open_bloc_id=open_bloc.id if open_bloc and score.bloc_bonus else None,
    )
