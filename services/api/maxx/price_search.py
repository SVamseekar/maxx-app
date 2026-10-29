"""How a scan finds comparable offers on the web and decides which of them to trust.

Retrieval follows Tavily's guidance (short keyword queries, search first, read only chosen pages)
and was tuned on live searches for real products on 30 Oct 2026:

- One search, biased toward shops. Sites that cannot sell the item are excluded and a list of US
  retailers and brand stores is preferred (include_domains_mode "prefer"), so shop pages rise
  without hiding small stores: a Ninja AF101 search went from 2 results to 10. Full page text
  comes with the search at no extra credit (include_raw_content; usage still showed 1 credit), so
  most pages never need a separate read.
- The score needs two stores that confirm price, stock and shipping, and only stores whose pages
  can be read can confirm anything. So when the first search finds fewer than two such stores, a
  second search asks only those stores (include_domains_mode "restrict"). For a Sony WH-1000XM5
  it added Crutchfield's in-stock, free-shipping offer beside sony.com; quoting the model code
  instead (exact_match) found fewer usable pages, and returned none at all on all retailers.
- A page is read in full (extract, billed per success) only when the search gave neither its
  full text nor its stock and shipping, and never on stores that answer automated readers with
  bot checks: Amazon, Walmart, Target, Best Buy and Home Depot reads all came back empty.
- Asking for freshly fetched pages (max_age_hours) was tried and dropped: it cut one search to
  four unpriced results.

Trust is decided in code, whatever the model says. An offer must come from a product page (a
search or category page lists many products and prices); its price must be quoted from that
page; and an offer for another brand, model code, model word (Pro, Max...) or pack size is not the
same item. This is the usual product-matching order: identifiers first, conflicting attributes
veto.
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
# US retailers and brand stores the search prefers. Others still appear.
RETAILERS = (
    "amazon.com",
    "walmart.com",
    "target.com",
    "bestbuy.com",
    "costco.com",
    "samsclub.com",
    "homedepot.com",
    "lowes.com",
    "bhphotovideo.com",
    "adorama.com",
    "newegg.com",
    "crutchfield.com",
    "abt.com",
    "macys.com",
    "kohls.com",
    "jcpenney.com",
    "staples.com",
    "officedepot.com",
    "qvc.com",
    "wayfair.com",
    "williams-sonoma.com",
    "crateandbarrel.com",
    "surlatable.com",
    "nordstrom.com",
    "dickssportinggoods.com",
    "rei.com",
    "gamestop.com",
    "worldwidestereo.com",
    "apple.com",
    "samsung.com",
    "sony.com",
    "bose.com",
    "dell.com",
    "hp.com",
    "lenovo.com",
    "microsoft.com",
    "ninjakitchen.com",
    "sharkninja.com",
    "dyson.com",
    "kitchenaid.com",
    "chewy.com",
    "ulta.com",
    "sephora.com",
    "zappos.com",
    "nike.com",
    "ikea.com",
)
# Makers' own stores. An offer the maker's store confirms is authoritative for that item, the way
# comparison sites mark an official store; the fixed list keeps lookalike domains out.
BRAND_STORES = (
    "apple.com",
    "samsung.com",
    "sony.com",
    "bose.com",
    "dell.com",
    "hp.com",
    "lenovo.com",
    "microsoft.com",
    "ninjakitchen.com",
    "sharkninja.com",
    "dyson.com",
    "kitchenaid.com",
    "nike.com",
    "ikea.com",
)
# Stores whose product pages answer automated readers with bot checks or script shells: their
# search snippets are used, but reading the page costs credits and returns no price.
BOT_WALLED = ("amazon.com", "walmart.com", "target.com", "bestbuy.com", "homedepot.com")
# Stores that can confirm an offer: the retailers above minus the bot-walled ones, Macy's (it
# answered "Access Denied") and the warehouse and home stores assumed to block the same way.
READABLE_SHOPS = tuple(
    d
    for d in RETAILERS
    if d not in BOT_WALLED + ("macys.com", "lowes.com", "costco.com", "samsclub.com")
)
# How the large stores spell a product page. Anything else on those hosts lists many products.
PRODUCT_PATHS = {
    "amazon.com": r"/(?:dp|gp/product)/",
    "walmart.com": r"/ip/",
    "target.com": r"/p/",
    "bestbuy.com": r"/site/[^?]*\d+\.p|skuId=",
    "homedepot.com": r"/p/",
    "lowes.com": r"/pd/",
    "ebay.com": r"/itm/",
    "macys.com": r"/shop/product/",
    "kohls.com": r"/product/",
    "costco.com": r"\.product\.",
}
# Search, browse and category pages on other sites.
LISTING_PATH = re.compile(
    r"/s\?|/s/|[?&](?:k|q|query|searchterm|st|keyword)=|/search|searchpage|/browse/|/b/|/b\?|"
    r"/cp/|/clp/|/category/|/c/",
    re.I,
)

PRICE = re.compile(r"\$\s*\d|USD\s*\d")
# An offer counts as in stock when its page says so, lets you put it in the cart, or promises
# dispatch or pickup (stores such as sony.com never print "in stock").
STOCK = re.compile(
    r"\bin[ -]stock\b|available to ship|ready to ship|add to (?:cart|bag)|ships within \d|"
    r"pickup (?:as early as )?today",
    re.I,
)
FREE_SHIPPING = re.compile(
    r"free (?:standard |\d-day |2-day |next-day )?(?:shipping|delivery)|ships free|"
    r"shipping\s*:?\s*\$0(?:\.00)?(?!\d)",
    re.I,
)
# What can follow "free shipping" and limit it: an order minimum, or a membership or card.
FREE_OVER = re.compile(r"(?:orders?|purchases?)\s+(?:over|above|of)\s+\$\s*(\d[\d,]*)", re.I)
FREE_FOR_MEMBERS = re.compile(r"\bmembers?\b|\bplus\b|\bcircle\b|\bprime\b|with (?:a )?card", re.I)
PAID_SHIPPING = r"shipping\s*:?\s*\$\s*{amount}"
# Labels that make an offer something other than a new, one-off USD purchase: other conditions,
# auctions and other currencies. They come before the price or in the offer's title.
NOT_NEW = re.compile(
    r"\b(?:refurbished|renewed|used|pre-owned|open[- ]box|scratch (?:&|and) dent|for parts|"
    r"auction|CAD|AUD|HKD|SGD|EUR|GBP)\b|\b\d+ bids?\b|[€£₹]",
    re.I,
)
# A price that needs a card, coupon, trade-in, membership or instalments. The condition follows
# the price: Home Depot's "$94.99 after $25 OFF ... upon opening a new card" was read as a plain
# price once.
CONDITIONAL = re.compile(
    r"after \$\s?\d[\d,.]* off|\b(?:upon opening|new card|clip coupon|with (?:a )?coupon|"
    r"promo code|trade-?in|member price|membership price)\b|"
    r"\$\s?\d[\d,.]*\s*(?:/\s?mo\b|per month)",
    re.I,
)
# Said next to the offer's price, the item cannot be bought now. Crutchfield's WH-1000XM5 page
# said "on backorder" while its comparison table said "In stock" for other models.
NOT_AVAILABLE = re.compile(
    r"back-?order|out of stock|sold out|notify me|pre-?order|coming soon|currently unavailable",
    re.I,
)
# Besides its prices, a long page keeps one passage for each of these: what the score needs.
SIGNALS = (STOCK, FREE_SHIPPING, re.compile(r"shipping\s*:?\s*\$\s*\d", re.I))
# Markdown images and link targets: long URLs that say nothing about the offer.
MARKUP = (re.compile(r"!\[[^\]]*\]\([^)]*\)"), re.compile(r"\[([^\]]*)\]\([^)]*\)"))
# Bot checks and consent walls come back as ordinary pages; their text proves nothing.
BLOCKED = re.compile(
    r"captcha|robot check|are you a (?:human|robot)|verify you are (?:a )?human|access denied|"
    r"press (?:and|&) hold|open prime modal|enable (?:javascript|cookies) to continue",
    re.I,
)
# A condition label comes just before its own price ("Open Box: $277.14", "Renewed from $229");
# availability can sit on either side of it ("On backorder ... $298.00", "$348.00 In stock").
CONDITION_REACH = 150
AVAILABILITY_REACH = 200
CONDITIONAL_REACH = 100
EVIDENCE_LIMIT = 4000
MAX_SOURCES = 10
ENOUGH_STORES = 2
MODEL_WORDS = {"pro", "max", "mini", "plus", "ultra", "lite", "se", "xl", "air", "slim", "neo"}
COLOURS = {
    "black",
    "white",
    "silver",
    "gray",
    "grey",
    "blue",
    "navy",
    "red",
    "green",
    "pink",
    "gold",
    "rose",
    "purple",
    "beige",
    "brown",
    "yellow",
    "orange",
    "midnight",
    "graphite",
    "charcoal",
    "cream",
    "ivory",
    "teal",
    "bronze",
    "copper",
    "platinum",
    "titanium",
    "sand",
    "smoky",
}
PACK = re.compile(r"\b(\d+)\s*-?\s*(?:pack|pk|count|ct)\b|\bpack of (\d+)\b|\bset of (\d+)\b", re.I)


def excluded_domains(history: bool) -> list[str]:
    return list(NOT_SHOPS if history else NOT_SHOPS + PRICE_TRACKERS)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _on(url: str, domains) -> str | None:
    host = _host(url)
    return next((d for d in domains if host == d or host.endswith("." + d)), None)


def sells_items(url: str, history: bool = False) -> bool:
    """False for excluded sites and their subdomains (Tavily's filter may not cover them)."""
    return _on(url, excluded_domains(history)) is None


def official_store(url: str, brand: str | None) -> bool:
    """True when the page is on the maker's own store for this brand (sony.com for Sony)."""
    store = _on(url, BRAND_STORES)
    if not store or not brand:
        return False
    name, label = _compact(brand), store.split(".")[0]
    return label == name or (len(name) >= 4 and name in label)


def product_page(url: str) -> bool:
    """True for a page about one product; false for search, browse and category pages."""
    store = _on(url, PRODUCT_PATHS)
    if store:
        return bool(re.search(PRODUCT_PATHS[store], url, re.I))
    parts = urlparse(url)
    return not LISTING_PATH.search(parts.path + ("?" + parts.query if parts.query else ""))


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def model_code(item) -> str | None:
    """The longest model word that carries a digit (WH-1000XM5, AF101), or None."""
    codes = [w for w in (item.model or "").split() if re.search(r"\d", w) and len(_compact(w)) >= 3]
    return max(codes, key=len) if codes else None


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
    payload = {
        "query": search_query(item, history),
        "search_depth": "basic",
        "max_results": 10,
        "chunks_per_source": 3,
        "country": "united states",
        "exclude_domains": excluded_domains(history),
        "include_raw_content": "markdown",
    }
    if not history:
        payload |= {"include_domains": list(RETAILERS), "include_domains_mode": "prefer"}
    return payload


def verifiable_payload(item) -> dict | None:
    """The second search: brand and model, asked only of stores whose pages can be read. None
    without a brand or model, since a generic name would only find other products."""
    if not (item.brand or item.model):
        return None
    return {
        "query": " ".join(filter(None, [item.brand, item.model, "price"])),
        "search_depth": "basic",
        "max_results": 10,
        "chunks_per_source": 3,
        "country": "united states",
        "include_domains": list(READABLE_SHOPS),
        "include_domains_mode": "restrict",
        "include_raw_content": "markdown",
    }


def blocked_page(text: str) -> bool:
    return len(text.strip()) < 40 or bool(BLOCKED.search(text[:3000]))


def free_shipping(text: str, price) -> bool:
    """True when the page offers free shipping that covers this price: no order minimum above it,
    and not only for members or card holders."""
    for match in FREE_SHIPPING.finditer(text):
        tail = text[match.end() : match.end() + 60]
        if FREE_FOR_MEMBERS.search(tail):
            continue
        minimum = FREE_OVER.search(tail)
        if minimum is None or float(minimum.group(1).replace(",", "")) <= float(price):
            return True
    return False


def _spans(text: str, pattern, reach: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        start, end = max(0, match.start() - reach), match.end() + reach
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    return spans


def evidence_text(title: str, snippet: str, raw: str, item) -> str:
    """What the model reads about one page: its title and snippet, then from the full text the
    passages around prices (those naming the product first) and one passage each stating stock
    and shipping, wherever on the page they are. Every quote the model returns must come from
    this text."""
    parts = [title.strip(), snippet.strip()]
    if raw and not blocked_page(raw):
        raw = MARKUP[1].sub(r"\1", MARKUP[0].sub("", raw))
        names = [t for t in (_compact(model_code(item) or ""), _compact(item.brand or "")) if t]
        prices = _spans(raw, PRICE, 250)
        prices.sort(key=lambda s: -sum(n in _compact(raw[s[0] : s[1]]) for n in names))
        parts += [raw[a:b].strip() for a, b in sorted(prices[:4])]
        for signal in SIGNALS:
            found = _spans(raw, signal, 120)
            if found:
                parts.append(raw[found[0][0] : found[0][1]].strip())
    return "\n[...]\n".join(p for p in parts if p)[:EVIDENCE_LIMIT]


def build_sources(results: list[dict], item, history: bool = False) -> list[dict]:
    """Search results reduced to product pages from sites that sell, one entry per URL."""
    sources, seen = [], set()
    for result in results:
        url = result.get("url", "")
        if not url.startswith("https://") or url in seen:
            continue
        if not sells_items(url, history) or not product_page(url):
            continue
        seen.add(url)
        if BLOCKED.search(result.get("title", "")):
            continue  # an "Access Denied" page has no offer, whatever its body says
        raw = result.get("raw_content") or ""
        sources.append(
            {
                "url": url,
                "content": evidence_text(
                    result.get("title", ""), result.get("content", ""), raw, item
                ),
                "full": bool(raw) and not blocked_page(raw),
            }
        )
    return sources


def _names_item(source: dict, item) -> bool:
    name = _compact(model_code(item) or item.brand or "")
    return not name or name in _compact(source["content"])


def confirmable_stores(sources: list[dict], item) -> int:
    """Stores that could pass the score's checks: a readable page naming the product with a price,
    stock wording and free shipping. The score needs two different stores."""
    return len(
        {
            _host(s["url"])
            for s in sources
            if not _on(s["url"], BOT_WALLED)
            and _names_item(s, item)
            and PRICE.search(s["content"])
            and STOCK.search(s["content"])
            and FREE_SHIPPING.search(s["content"])
        }
    )


def merge_sources(first: list[dict], more: list[dict]) -> list[dict]:
    urls = {s["url"] for s in first}
    return first + [s for s in more if s["url"] not in urls]


def rank_sources(sources: list[dict], item) -> list[dict]:
    """Priced pages that name the product first, at most MAX_SOURCES for the model to read."""
    ranked = sorted(
        sources, key=lambda s: (not PRICE.search(s["content"]), not _names_item(s, item))
    )
    return ranked[:MAX_SOURCES]


def extract_targets(sources: list[dict], limit: int = 2) -> list[str]:
    """Pages to read in full: readable product pages whose full text the search did not return.
    Priced pages that do not yet show both stock and shipping (which the score needs) come
    first, then unpriced ones. Bot-walled stores are never read."""
    readable = [s for s in sources if not s.get("full") and not _on(s["url"], BOT_WALLED)]
    complete = {
        s["url"]
        for s in readable
        if STOCK.search(s["content"]) and FREE_SHIPPING.search(s["content"])
    }
    priced = [s["url"] for s in readable if PRICE.search(s["content"]) and s["url"] not in complete]
    unpriced = [s["url"] for s in readable if not PRICE.search(s["content"])]
    return (priced + unpriced)[:limit]


def extract_payload(item, urls: list[str], history: bool = False) -> dict:
    return {
        "urls": urls,
        "extract_depth": "advanced",
        "query": search_query(item, history) + " shipping in stock",
        "chunks_per_source": 3,
        # Below the provider timeout, so a slow page ends the extract and not the whole search.
        "timeout": 12,
    }


def _at(text: str, evidence: str) -> int:
    return text.find(evidence) if evidence else -1


def before_offer(text: str, evidence: str) -> str:
    """The quoted price and the text just before it, where that offer's condition is labelled.
    Labels after the price belong to the next offer on the page."""
    at = _at(text, evidence)
    return text if at < 0 else text[max(0, at - CONDITION_REACH) : at + len(evidence)]


def after_offer(text: str, evidence: str) -> str:
    """The quoted price and the text just after it, where a price's conditions are written."""
    at = _at(text, evidence)
    return text if at < 0 else text[at : at + len(evidence) + CONDITIONAL_REACH]


def around_offer(text: str, evidence: str) -> str:
    """The text on both sides of the quoted price, where that offer's availability is stated."""
    at = _at(text, evidence)
    if at < 0:
        return text
    return text[max(0, at - AVAILABILITY_REACH) : at + len(evidence) + AVAILABILITY_REACH]


def _pack(text: str) -> int:
    match = PACK.search(text or "")
    return int(next(g for g in match.groups() if g)) if match else 1


def variant_conflict(item, row) -> str | None:
    """Why the offer is for another product, or None. Each check applies only when the scanned item
    states the attribute: brand, digit-bearing model codes, model words, pack size and colour."""
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
    wanted = _colours(item.variant) or _colours(item.title)
    listed = _colours(row.title)
    if wanted and listed and not wanted & listed:
        return "colour_mismatch"
    return None


def _colours(text: str | None) -> set[str]:
    return {"gray" if w == "grey" else w for w in _words(text) & COLOURS}
