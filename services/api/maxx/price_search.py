"""How a scan looks for comparable offers: the Tavily requests, which pages to read in full, and
the deterministic checks that keep a different product out of the comparison.

Tavily's guidance: short keyword queries, exclude sites that cannot sell the item, search first and
extract only chosen pages with a query so the returned chunks sit next to the price. Price
comparison practice: an offer for another model, model word or pack size is never the same item,
however similar its title (match on identifiers, veto on conflicting attributes).
"""

import re
from urllib.parse import urlparse

# Sites that talk about prices without selling the item: news, finance, reference, reviews,
# video, social and company databases. Their numbers are often for other models or other dates.
NOT_SHOPS = (
    "wikipedia.org",
    "youtube.com",
    "reddit.com",
    "quora.com",
    "medium.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "finance.yahoo.com",
    "investing.com",
    "marketwatch.com",
    "bloomberg.com",
    "reuters.com",
    "cnbc.com",
    "forbes.com",
    "businessinsider.com",
    "theverge.com",
    "engadget.com",
    "wired.com",
    "cnet.com",
    "techradar.com",
    "tomsguide.com",
    "rtings.com",
    "whathifi.com",
    "pcguide.com",
    "pcmag.com",
    "tomshardware.com",
    "zdnet.com",
    "slickdeals.net",
    "dealnews.com",
    "cbinsights.com",
    "crunchbase.com",
)
# Price trackers show a price history, not an offer: kept for history searches only.
PRICE_TRACKERS = ("camelcamelcamel.com", "keepa.com")
# Stores whose product pages answer automated readers with bot checks or script shells: their
# search snippets are used, but reading the page costs credits and returns no price.
BOT_WALLED = ("amazon.com", "walmart.com")

PRICE = re.compile(r"\$\s*\d|USD\s*\d")
# An offer counts as in stock when its page says so, lets you put it in the cart, or promises
# dispatch or pickup (stores such as sony.com never print "in stock").
STOCK = re.compile(
    r"\bin[ -]stock\b|available to ship|ready to ship|add to (?:cart|bag)|ships within \d|"
    r"pickup (?:as early as )?today",
    re.I,
)
FREE_SHIPPING = re.compile(
    r"free (?:standard )?(?:shipping|delivery)|ships free|shipping\s*:?\s*\$0(?:\.00)?(?!\d)", re.I
)
PAID_SHIPPING = r"shipping\s*:?\s*\$\s*{amount}"
# Bot checks and consent walls come back as ordinary pages; their text proves nothing.
BLOCKED = re.compile(
    r"captcha|robot check|are you a (?:human|robot)|verify you are (?:a )?human|access denied|"
    r"press (?:and|&) hold|open prime modal|enable (?:javascript|cookies) to continue",
    re.I,
)
OFFER_REACH = 400
MODEL_WORDS = {"pro", "max", "mini", "plus", "ultra", "lite", "se", "xl", "air", "slim", "neo"}
PACK = re.compile(r"\b(\d+)\s*-?\s*(?:pack|pk|count|ct)\b|\bpack of (\d+)\b|\bset of (\d+)\b", re.I)


def excluded_domains(history: bool) -> list[str]:
    return list(NOT_SHOPS if history else NOT_SHOPS + PRICE_TRACKERS)


def _on(url: str, domains) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def sells_items(url: str, history: bool = False) -> bool:
    """False for excluded sites and their subdomains (Tavily's filter may not cover them)."""
    return not _on(url, excluded_domains(history))


def search_query(item, history: bool = False) -> str:
    """Brand, model, variant and title once each, as a short keyword query."""
    words, seen = [], set()
    for part in (item.brand, item.model, item.variant, item.title):
        for word in (part or "").split():
            key = re.sub(r"\W", "", word.lower())
            if key and key not in seen:
                seen.add(key)
                words.append(word)
    return " ".join(words)[:300] + (" price history" if history else " price buy new")


def search_payload(item, history: bool = False) -> dict:
    return {
        "query": search_query(item, history),
        "search_depth": "basic",
        "max_results": 8,
        "chunks_per_source": 3,
        "country": "united states",
        "exclude_domains": excluded_domains(history),
    }


def extract_targets(sources: list[dict], limit: int = 3) -> list[str]:
    """Pages to read in full. First priced pages that do not yet show both stock and shipping,
    which the score needs (a priced snippet means the page is readable), then unpriced pages.
    Bot-walled stores are never read."""
    readable = [s for s in sources if not _on(s["url"], BOT_WALLED)]
    complete = [
        s["url"]
        for s in readable
        if STOCK.search(s["content"]) and FREE_SHIPPING.search(s["content"])
    ]
    priced = [s["url"] for s in readable if PRICE.search(s["content"])]
    unpriced = [s["url"] for s in readable if s["url"] not in priced]
    picked = [u for u in priced if u not in complete][:limit]
    return picked + unpriced[: limit - len(picked)]


def extract_payload(item, urls: list[str], history: bool = False) -> dict:
    return {
        "urls": urls,
        "extract_depth": "advanced",
        "query": search_query(item, history) + " shipping in stock",
        "chunks_per_source": 3,
        # Below the provider timeout, so a slow page ends the extract and not the whole search.
        "timeout": 12,
    }


def blocked_page(text: str) -> bool:
    return len(text.strip()) < 40 or bool(BLOCKED.search(text[:3000]))


def offer_window(text: str, evidence: str) -> str:
    """The part of the page around the quoted price, where that offer's condition is stated."""
    at = text.find(evidence) if evidence else -1
    if at < 0:
        return text
    return text[max(0, at - OFFER_REACH) : at + len(evidence) + OFFER_REACH]


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _pack(text: str) -> int:
    match = PACK.search(text or "")
    return int(next(g for g in match.groups() if g)) if match else 1


def variant_conflict(item, row) -> str | None:
    """Why the offer is for another product, or None. Each check applies only when the scanned item
    states the attribute: brand, digit-bearing model codes, model words and pack size."""
    offer = f"{row.title} {row.evidence}"
    if item.brand and _compact(item.brand) not in _compact(offer):
        return "brand_mismatch"
    for code in (_compact(w) for w in (item.model or "").split()):
        if any(c.isdigit() for c in code) and code not in _compact(offer):
            return "model_mismatch"
    named = _words(" ".join(filter(None, [item.title, item.model, item.variant])))
    if (MODEL_WORDS & _words(row.title)) - named:
        return "model_word_mismatch"
    if _pack(row.title) != _pack(item.title):
        return "pack_mismatch"
    return None
