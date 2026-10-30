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
from maxx.price_search import (
    CONDITIONAL,
    ENOUGH_STORES,
    NOT_AVAILABLE,
    NOT_NEW,
    PAID_SHIPPING,
    STOCK,
    after_offer,
    around_offer,
    before_offer,
    blocked_page,
    build_sources,
    confirmable_stores,
    evidence_text,
    extract_payload,
    extract_targets,
    free_shipping,
    merge_sources,
    rank_sources,
    search_payload,
    variant_conflict,
    verifiable_payload,
)
from maxx.providers import BudgetExceeded, ProviderError, chat, log_guard, request
from maxx.scan import (
    MEANINGS,
    Contract,
    Identity,
    Item,
    Move,
    PriceRow,
    ScanResult,
    VisionItem,
    money_score,
    official_only,
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
        # Reject non-retail condition, auctions and other currencies (labelled in the title or just
        # before the quoted price; a store page often lists renewed or open-box offers next to the
        # new one) and prices that need a card or coupon (written just after the price).
        if (
            NOT_NEW.search(row.title)
            or NOT_NEW.search(before_offer(text, row.evidence))
            or CONDITIONAL.search(after_offer(text, row.evidence))
        ):
            row.same_item = False
        # Free shipping is decided by the page's own wording, whatever the model said; a paid
        # amount must be quoted next to the word shipping.
        if not row.shipping:
            row.shipping = Decimal(0) if free_shipping(text, row.price) else None
        elif not re.search(PAID_SHIPPING.format(amount=re.escape(str(row.shipping))), text, re.I):
            row.shipping = None
        row.in_stock = (
            row.in_stock
            and bool(STOCK.search(text))
            and not NOT_AVAILABLE.search(around_offer(text, row.evidence))
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
    if not (item.brand or item.model):
        warnings.append(
            "Without a brand and model the web search finds similar products, not this one. "
            "Add them under Edit extracted details for a real comparison."
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
    search = "https://api.tavily.com/search"
    data = await request(
        client, request_id, calls, "tavily", "search", search, search_payload(item, history)
    )
    sources = build_sources(data.get("results", []), item, history)
    fired = []
    second = None if history else verifiable_payload(item)
    if second and confirmable_stores(sources, item) < ENOUGH_STORES:
        # Too few stores could confirm an offer: ask only the stores whose pages can be read.
        try:
            more = await request(client, request_id, calls, "tavily", "search", search, second)
            sources = merge_sources(sources, build_sources(more.get("results", []), item, history))
        except ProviderError:
            fired.append("second_search_failed")
    sources = rank_sources(sources, item)
    targets = extract_targets(sources)
    if targets:
        try:
            extracted = await request(
                client,
                request_id,
                calls,
                "tavily",
                "extract",
                "https://api.tavily.com/extract",
                extract_payload(item, targets, history),
            )
        except ProviderError:
            # Reading pages in full only adds evidence; the search results still stand.
            extracted = {}
            fired.append("extract_failed")
        pages = {r.get("url"): r.get("raw_content") or "" for r in extracted.get("results", [])}
        for source in sources:
            page = pages.get(source["url"])
            if page is None:
                continue
            if blocked_page(page):
                fired.append("blocked_page")
            else:
                source["content"] = evidence_text(source["content"], "", page, item)
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
            "sources": [{"url": src["url"], "content": src["content"]} for src in sources],
        },
        Rows,
    )
    rows = ground_rows(parsed.rows, sources, fired)
    for row in rows:
        reason = variant_conflict(item, row) if row.same_item else None
        if reason:
            row.same_item = False
            fired.append(reason)
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
    manifest = json.loads((ROOT / "evals/fixtures.json").read_text())
    case = next((c for c in manifest if c["sha256"] == hashlib.sha256(data).hexdigest()), None)
    # The samples show made-up products that no live search can find, so even in live mode they
    # replay their recorded result, labelled as demo prices.
    mode = "fixture" if case is not None else settings.scan_mode
    if mode == "fixture":
        if case is None:
            raise ProviderError(
                "Fixture mode accepts only the supplied sample screenshots. Configure"
                " live mode for your own images."
            )
        item = Item.model_validate(case["item"])
        rows = [PriceRow.model_validate(r) for r in case["rows"]]
        warnings.append(
            "Sample replay: this sample's recorded demo prices, with no live calls. For live "
            "prices, upload a screenshot of a branded product page or cart."
            if settings.scan_mode == "live"
            else "Fixture replay: extraction and prices are canned test data, not live provider "
            "results."
        )
    elif mode == "live":
        if not settings.nebius_api_key or not settings.tavily_api_key:
            raise ProviderError(
                "Live scanning is not configured. Set NEBIUS_API_KEY and TAVILY_API_KEY "
                "(see .env.example)."
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
            score = money_score(item.price, rows, owns, brand=item.brand)
            move = template_move(item, score, rows)
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
                            "meaning": MEANINGS[move.primary],
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
            return finish(item, rows, owns, request_id, calls, warnings, started, move, mode)
    else:
        raise ProviderError("SCAN_MODE must be live or fixture.")
    if corrections:
        if corrections.get("title", item.title) != item.title:
            rows = []
        item = item.model_copy(update=corrections)
    return finish(item, rows, owns, request_id, calls, warnings, started, mode=mode)


def finish(item, rows, owns, request_id, calls, warnings, started, move=None, mode=None):
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
        item.brand,
    )
    if score.bloc_bonus:
        move = template_move(item, score, rows)
    if not item.title or not item.price:
        warnings.append(
            "Product or price could not be read. Edit the details or upload a clearer screenshot."
        )
    if item.currency != "USD":
        warnings.append("This milestone supports USD only; no currency conversion is inferred.")
    if official_only(rows, item.brand):
        warnings.append(
            "Scored against the maker's own store: no second store confirmed stock and shipping."
        )
    if score.low_confidence:
        warnings.append(
            "Fewer than two independent comparable listings with known shipping "
            "and stock. Low confidence."
        )
    return ScanResult(
        request_id=request_id,
        mode=mode or settings.scan_mode,
        item=item,
        rows=rows,
        score=score,
        recommendation=move or template_move(item, score, rows),
        warnings=warnings,
        latency_ms=round((time.perf_counter() - started) * 1000),
        calls=calls,
        open_bloc_id=open_bloc.id if open_bloc and score.bloc_bonus else None,
    )
