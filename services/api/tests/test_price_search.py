import asyncio
import json
from decimal import Decimal

import httpx2 as httpx
from fastapi.testclient import TestClient

from maxx import flow
from maxx.main import app
from maxx.price_search import (
    blocked_page,
    build_sources,
    confirmable_stores,
    evidence_text,
    extract_payload,
    extract_targets,
    free_shipping,
    product_page,
    search_payload,
    search_query,
    sells_items,
    variant_conflict,
    verifiable_payload,
)
from maxx.scan import Item, PriceRow, money_score, template_move

SONY = Item(
    title="Sony WH-1000XM5 Wireless Noise Canceling Headphones Black",
    brand="Sony",
    model="WH-1000XM5",
    variant="Black",
    price="399.99",
    currency="USD",
)


def offer(title, evidence="$348.00 In stock. Free shipping.", url="https://shop.example/x"):
    return PriceRow(
        title=title,
        url=url,
        price="348",
        shipping="0",
        same_item=True,
        in_stock=True,
        evidence=evidence,
    )


def chat_rows(rows):
    content = json.dumps({"rows": [r.model_dump(mode="json") for r in rows]})
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_the_first_search_prefers_shops_and_brings_full_page_text():
    assert search_query(SONY) == (
        "Sony WH-1000XM5 Black Wireless Noise Canceling Headphones price buy new"
    )
    payload = search_payload(SONY)
    assert payload["country"] == "united states" and payload["max_results"] == 10
    assert payload["search_depth"] == "basic" and payload["chunks_per_source"] == 3
    assert (
        payload["include_domains_mode"] == "prefer" and "bestbuy.com" in payload["include_domains"]
    )
    assert payload["include_raw_content"] == "markdown"
    assert "investing.com" in payload["exclude_domains"]
    assert "camelcamelcamel.com" in payload["exclude_domains"]
    history = search_payload(SONY, history=True)
    assert "camelcamelcamel.com" not in history["exclude_domains"]
    assert "include_domains" not in history


def test_the_second_search_asks_only_stores_whose_pages_can_be_read():
    payload = verifiable_payload(SONY)
    assert payload["query"] == "Sony WH-1000XM5 price"
    assert payload["include_domains_mode"] == "restrict" and "exact_match" not in payload
    assert (
        "crutchfield.com" in payload["include_domains"] and "sony.com" in payload["include_domains"]
    )
    assert not {"amazon.com", "walmart.com", "macys.com"} & set(payload["include_domains"])
    assert verifiable_payload(Item(title="Wireless Headphones")) is None


def test_only_product_pages_on_sites_that_sell_are_kept():
    assert not sells_items("https://ca.investing.com/news/sony")
    assert not sells_items("https://en.wikipedia.org/wiki/Sony")
    assert not sells_items("https://camelcamelcamel.com/product/B09XS7JWHH")
    assert sells_items("https://camelcamelcamel.com/product/B09XS7JWHH", history=True)
    assert product_page("https://www.target.com/p/ninja-af101/-/A-12345")
    assert not product_page("https://www.target.com/s?searchTerm=ninja+af101")
    assert product_page("https://www.amazon.com/dp/B09XS7JWHH")
    assert not product_page("https://www.amazon.com/clp/B09XS7JWHH")
    assert product_page("https://www.walmart.com/ip/Sony-WH-1000XM5/386006068")
    assert product_page("https://electronics.sony.com/audio/headphones/headband/p/wh1000xm5-b")
    assert product_page("https://listenup.com/products/sony-wh-1000xm5")
    assert not product_page("https://smallshop.example/search?q=sony")
    assert not product_page("https://smallshop.example/category/headphones")


def test_evidence_keeps_the_passages_that_price_and_describe_this_offer():
    filler = "Specs and reviews. " * 60
    raw = (
        "Menu Cart Gift cards $25 off your first order "
        + filler
        + "Sony WH-1000XM5 Black Sale Price $228.00 Original Price $399.99 "
        + filler
        + "![badge](https://cdn.example/a.png) Pickup As Early As Today "
        + filler
        + "[Free Shipping](https://shop.example/shipping) on every order."
    )
    text = evidence_text("WH-1000XM5 | Black", "Sony WH-1000XM5 from $228", raw, SONY)
    assert text.startswith("WH-1000XM5 | Black")
    assert "Sale Price $228.00" in text and "Pickup As Early As Today" in text
    assert "Free Shipping" in text
    assert len(text) <= 4000 and text.count("Specs and reviews.") < 60
    assert evidence_text("T", "S", "Robot Check. Type the characters.", SONY) == "T\n[...]\nS"


def test_search_results_become_one_source_per_product_page():
    results = [
        {
            "url": "https://shop.example/p/1",
            "title": "Sony WH-1000XM5",
            "content": "$348.00",
            "raw_content": "Sony WH-1000XM5 Black $348.00 In stock. Free shipping today.",
        },
        {"url": "https://shop.example/p/1", "title": "duplicate", "content": "$1"},
        {"url": "https://www.businessinsider.com/review", "title": "Review", "content": "$298"},
        {"url": "https://www.target.com/s?searchTerm=sony", "title": "Search", "content": "$99"},
        {"url": "https://other.example/item", "title": "Sony WH-1000XM5", "content": "Sony"},
    ]
    sources = build_sources(results, SONY)
    assert [s["url"] for s in sources] == ["https://shop.example/p/1", "https://other.example/item"]
    assert sources[0]["full"] and not sources[1]["full"]
    assert confirmable_stores(sources, SONY) == 1


def test_pages_are_read_in_full_only_when_the_search_could_not():
    sources = [
        {
            "url": "https://a.example/p",
            "content": "$348.00 In stock. Free shipping.",
            "full": False,
        },
        {"url": "https://b.example/p", "content": "$349.99 Add to cart", "full": False},
        {"url": "https://c.example/p", "content": "See price in cart", "full": False},
        {"url": "https://d.example/p", "content": "$350.00", "full": True},
        {"url": "https://www.bestbuy.com/site/x/6505727.p", "content": "$329.99", "full": False},
    ]
    assert extract_targets(sources) == ["https://b.example/p", "https://c.example/p"]
    payload = extract_payload(SONY, ["https://b.example/p"])
    assert payload["extract_depth"] == "advanced" and payload["chunks_per_source"] == 3
    assert payload["query"].endswith("shipping in stock") and payload["timeout"] < 20


def test_bot_checks_and_empty_pages_are_not_evidence():
    assert blocked_page("Robot Check. Enter the characters you see below.")
    assert blocked_page("open prime modal")
    assert blocked_page("   ")
    assert not blocked_page("Sony WH-1000XM5 Black $348.00 In stock. Free shipping on this item.")


def test_another_model_model_word_pack_size_or_brand_is_not_the_same_item():
    assert variant_conflict(SONY, offer("Sony WH-1000XM5/B Headphones, Black")) is None
    assert variant_conflict(SONY, offer("Sony WH-1000XM4 Headphones, Black")) == "model_mismatch"
    assert variant_conflict(SONY, offer("Bose QuietComfort Ultra WH-1000XM5 case")) == (
        "brand_mismatch"
    )
    pods = Item(title="Apple AirPods 4", brand="Apple", model="AirPods 4", price="129")
    assert variant_conflict(pods, offer("Apple AirPods Pro 4")) == "model_word_mismatch"
    assert variant_conflict(SONY, offer("Sony WH-1000XM5 Black, 2-Pack")) == "pack_mismatch"
    assert variant_conflict(SONY, offer("Sony WH-1000XM5 Wireless Headphones in Silver")) == (
        "colour_mismatch"
    )
    assert variant_conflict(SONY, offer("Sony WH-1000XM5 (Black/Grey)")) is None


def test_condition_counts_only_around_the_offer_and_auctions_are_not_retail():
    page = (
        "Sony WH-1000XM5 Black $348.00 In stock. Free shipping. "
        + "Specs and reviews. " * 40
        + "Also available: Renewed from $229.00"
    )
    source = {"url": "https://shop.example/x", "content": page}
    row = offer("Sony WH-1000XM5 Black", evidence="Sony WH-1000XM5 Black $348.00 In stock.")
    assert flow.ground_rows([row], [source])[0].same_item
    for wording in ("Renewed:", "Open Box", "Pre-Owned", "3 bids ·"):
        near = {
            "url": source["url"],
            "content": f"{wording} Sony WH-1000XM5 Black $348.00 In stock.",
        }
        assert not flow.ground_rows([row.model_copy()], [near])[0].same_item, wording


def test_enough_offers_from_the_first_search_means_no_second_search():
    paths = []
    results = [
        {
            "url": f"https://shop{i}.example/p/xm5",
            "title": "Sony WH-1000XM5",
            "content": f"Sony WH-1000XM5 Black $34{i}.00 In stock. Free shipping.",
            "raw_content": f"Sony WH-1000XM5 Black $34{i}.00 In stock. Free shipping today only.",
        }
        for i in range(3)
    ]

    def transport(req):
        paths.append(req.url.path)
        if req.url.path == "/search":
            return httpx.Response(200, json={"results": results})
        return chat_rows(
            [
                offer("Sony WH-1000XM5 Black", r["content"], r["url"]).model_copy(
                    update={"price": Decimal(f"34{i}")}
                )
                for i, r in enumerate(results)
            ]
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            return await flow.comparable_prices(client, SONY, "test-enough", [])

    rows = asyncio.run(run())
    assert paths == ["/search", "/v1/chat/completions"]
    assert len(rows) == 3


def test_a_thin_first_search_asks_readable_stores_and_keeps_only_this_item():
    sent = []
    shop = "https://shop.example/xm5"
    walled = "https://www.walmart.com/ip/Sony-WH-1000XM5/386006068"
    other = "https://bigstore.example/p/1"

    def transport(req):
        body = json.loads(req.content)
        sent.append((req.url.path, body))
        if req.url.path == "/search" and body.get("include_domains_mode") == "prefer":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": shop,
                            "title": "Sony WH-1000XM5",
                            "content": "Sony WH-1000XM5 Black",
                            "raw_content": "Sony WH-1000XM5 Black $348.00 In stock. "
                            "Free shipping on it.",
                        },
                        {
                            "url": "https://www.businessinsider.com/sony",
                            "title": "Review",
                            "content": "$298",
                        },
                    ]
                },
            )
        if req.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": walled,
                            "title": "Sony WH-1000XM5",
                            "content": "current price $329.00",
                        },
                        {"url": other, "title": "Big Store", "content": "Sony WH-1000XM5 $310.00"},
                    ]
                },
            )
        if req.url.path == "/extract":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"url": other, "raw_content": "Robot Check. Type the characters you see."}
                    ],
                    "failed_results": [],
                },
            )
        return chat_rows(
            [
                offer("Sony WH-1000XM5 Black", "Sony WH-1000XM5 Black $348.00 In stock.", shop),
                offer("Sony WH-1000XM4 Black", "Sony WH-1000XM5 $310.00", other),
            ]
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            calls = []
            return await flow.comparable_prices(client, SONY, "test-thin", calls), calls

    rows, calls = asyncio.run(run())
    searches = [body for path, body in sent if path == "/search"]
    assert len(searches) == 2 and searches[1]["include_domains_mode"] == "restrict"
    # The walled store is never read; the page the search gave in full is not read again.
    extract = next(body for path, body in sent if path == "/extract")
    assert extract["urls"] == [other]
    read = json.loads(sent[-1][1]["messages"][1]["content"][0]["text"])["data"]["sources"]
    assert {s["url"] for s in read} == {shop, walled, other}
    assert [(r.url.host, r.same_item) for r in rows] == [("shop.example", True)]
    assert [c["purpose"] for c in calls] == ["search", "search", "extract", "extract"]


def test_a_slow_page_read_falls_back_to_the_search_snippets():
    shop = "https://shop.example/xm5"
    evidence = "Sony WH-1000XM5 Black $348.00 Free shipping."

    def transport(req):
        if req.url.path == "/search":
            # Stock is not in the snippet, so the page is read in full, and that read times out.
            return httpx.Response(200, json={"results": [{"url": shop, "content": evidence}]})
        if req.url.path == "/extract":
            raise httpx.ReadTimeout("slow page", request=req)
        return chat_rows([offer("Sony WH-1000XM5 Black", evidence, shop)])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            calls = []
            return await flow.comparable_prices(client, SONY, "test-slow", calls), calls

    rows, calls = asyncio.run(run())
    assert [(c["provider"], c["purpose"]) for c in calls] == [
        ("tavily", "search"),
        ("tavily", "search"),
        ("tavily", "extract"),
        ("nebius", "extract"),
    ]
    assert calls[2]["status"] != "ok"
    assert rows[0].price == Decimal("348") and rows[0].shipping == 0 and not rows[0].in_stock


def test_without_brand_or_model_the_scan_says_how_to_get_a_real_comparison():
    warnings = []

    def transport(req):
        return httpx.Response(200, json={"results": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            generic = Item(title="Wireless Headphones Black", price="199.99", currency="USD")
            return await flow.comparable_prices(
                client, generic, "test-generic", [], warnings=warnings
            )

    assert asyncio.run(run()) == []
    assert any("brand and model" in w for w in warnings)


def test_one_cheaper_listing_without_a_score_is_still_named():
    sale = offer("Sony WH-1000XM5", evidence="Sale Price $228.00").model_copy(
        update={"price": Decimal("228"), "in_stock": False}
    )
    score = money_score(Decimal("399.99"), [sale], False)
    move = template_move(SONY, score, [sale])
    assert score.low_confidence and move.primary == "WAIT"
    assert move.headline == "Seen for less elsewhere."
    assert "$228.00 delivered" in move.explanation and "$399.99" in move.explanation
    more = sale.model_copy(update={"price": Decimal("298"), "shipping": None})
    many = template_move(SONY, score, [more, sale]).explanation
    assert many.startswith("2 stores list this item for less: $228.00 to $298.00")
    assert "Shipping is not known for all of them." in many
    other = sale.model_copy(update={"same_item": False})
    assert template_move(SONY, score, [other]).headline == "Check the details before buying."


def test_add_to_cart_counts_as_stock_wording():
    source = {"url": "https://shop.example/x", "content": "Sony WH-1000XM5 $348.00 Add to Cart"}
    row = offer("Sony WH-1000XM5", evidence="Sony WH-1000XM5 $348.00")
    assert flow.ground_rows([row], [source])[0].in_stock


# Text read from electronics.sony.com on 30 Oct 2026: a sale price, free shipping, and pickup
# instead of the words "in stock"; the "/ mo" financing line sits next to the price.
SONY_STORE = (
    "Free Shipping & Extended ReturnsLearn more\n## Cart (0 product)\nProduct Details\n"
    "WH-1000XM5 Premium Wireless Noise Cancelling Headphones | Black\n$228.00~~$399.99~~\n/ mo\n"
    "Model: WH-1000XM5\nSale Price $228.00\nSave $171.99\nOriginal Price~~$399.99~~\n"
    "Color : Black\nBenefits of Buying Directly From Sony\nEasy Returns\nFree Shipping\n"
    "Starting 0% APR with Affirm\nPickup As Early As Today"
)


def test_a_real_store_page_with_a_sale_price_counts_as_a_trusted_offer():
    source = {"url": "https://electronics.sony.com/p/wh1000xm5-b", "content": SONY_STORE}
    row = PriceRow(
        title="Sony WH-1000XM5 Premium Wireless Noise Cancelling Headphones | Black",
        url=source["url"],
        price="228",
        shipping="0",
        same_item=True,
        in_stock=True,
        evidence="Sale Price $228.00",
    )
    grounded = flow.ground_rows([row], [source])
    assert grounded[0].same_item and grounded[0].in_stock and grounded[0].shipping == 0
    assert variant_conflict(SONY, grounded[0]) is None


def test_a_sample_screenshot_replays_its_recorded_result_in_live_mode(monkeypatch):
    from maxx.config import ROOT, settings

    monkeypatch.setattr(settings, "scan_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    case = json.loads((ROOT / "evals/fixtures.json").read_text())[0]
    response = TestClient(app).post(
        "/scan",
        content=(ROOT / "evals" / case["file"]).read_bytes(),
        headers={"content-type": "image/png"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "fixture" and body["calls"] == []
    assert any(w.startswith("Sample replay") for w in body["warnings"])
    assert body["score"]["value"] is not None


def test_advanced_tavily_requests_reserve_double_credits(monkeypatch):
    from maxx import budget, providers

    held = []
    monkeypatch.setattr(budget, "reserve_credits", lambda request_id, credits: held.append(credits))
    providers.reserve_for("r", "tavily", "search", {"search_depth": "basic"}, {})
    providers.reserve_for(
        "r", "tavily", "extract", {"urls": ["a", "b", "c"], "extract_depth": "advanced"}, {}
    )
    providers.reserve_for("r", "tavily", "extract", {"urls": ["a"] * 6}, {})
    assert held == [1, 2, 2]


def test_free_shipping_must_cover_this_price_and_not_need_a_membership():
    assert free_shipping("Free Shipping & Extended Returns", 228)
    assert free_shipping("Free shipping on orders over $35", 129.99)
    assert not free_shipping("Free shipping on orders over $35", 19.99)
    assert not free_shipping("Free shipping for Walmart+ members", 129.99)
    assert not free_shipping("Shipping calculated at checkout", 129.99)
    source = {
        "url": "https://shop.example/x",
        "content": "Sony WH-1000XM5 $348.00 In stock. Free 2-day shipping",
    }
    row = offer("Sony WH-1000XM5", evidence="Sony WH-1000XM5 $348.00").model_copy(
        update={"shipping": None}
    )
    assert flow.ground_rows([row], [source])[0].shipping == 0


# Home Depot's search snippet for the Ninja AF101 on 30 Oct 2026.
CARD_OFFER = (
    "NINJA Basket Electric Air Fryer, 4 qt. Black And Gray, Digital Temperature. "
    "Pay $94.99 after $25 OFF your total qualifying purchase upon opening a new card."
)


def test_a_price_that_needs_a_card_coupon_or_trade_in_is_not_a_retail_price():
    source = {"url": "https://www.homedepot.com/p/ninja/1", "content": CARD_OFFER}
    row = offer("NINJA Basket Electric Air Fryer", "Pay $94.99", source["url"]).model_copy(
        update={"price": Decimal("94.99"), "shipping": None}
    )
    assert not flow.ground_rows([row], [source])[0].same_item


def test_an_access_denied_page_is_dropped_whatever_its_body_says():
    results = [
        {
            "url": "https://www.macys.com/shop/product/ninja-af101?ID=1",
            "title": "Access Denied - Macy's",
            "content": "Ninja AF101 $99.99",
            "raw_content": "Shop by Department Women Men Kids Ninja AF101 $99.99 " * 3,
        }
    ]
    assert build_sources(results, SONY) == []


# Crutchfield's WH-1000XM5 page on 30 Oct 2026: on backorder, while a comparison table lower on
# the page says "In stock" for other models.
CRUTCHFIELD = (
    "The Sony WH-1000XM5 is on backorder\n\nOn backorder\n\n**Expected: 11/11/2026**\n\n"
    "Free shipping\n\nAmount was $398.00\n\nSale: $100.00 off\n\n$298.00\n\nBackorder now\n"
    "Open Box: $277.14\nScratch & Dent: $263.28\n"
    + "Specs. " * 80
    + "| Stock | On backorder | In stock |"
)


def test_a_backordered_offer_is_the_same_item_but_not_in_stock():
    source = {"url": "https://www.crutchfield.com/p_158100XM5B/x.html", "content": CRUTCHFIELD}
    row = offer("Sony WH-1000XM5 (Black)", "Sale: $100.00 off\n\n$298.00", source["url"])
    grounded = flow.ground_rows([row.model_copy(update={"price": Decimal("298")})], [source])[0]
    assert grounded.same_item and not grounded.in_stock and grounded.shipping == 0
    dent = offer("Sony WH-1000XM5 (Black)", "Scratch & Dent: $263.28", source["url"])
    assert not flow.ground_rows([dent.model_copy(update={"price": Decimal("263.28")})], [source])[
        0
    ].same_item


def test_a_monthly_price_is_conditional_but_a_financing_line_nearby_is_not():
    from maxx.price_search import CONDITIONAL, after_offer

    assert CONDITIONAL.search(after_offer("Plan $19.99/mo with service", "$19.99"))
    assert not CONDITIONAL.search(after_offer(SONY_STORE, "$228.00~~$399.99~~"))


def test_the_makers_own_store_can_confirm_an_offer_alone():
    from maxx.price_search import official_store

    assert official_store("https://electronics.sony.com/p/wh1000xm5-b", "Sony")
    assert official_store("https://www.sharkninja.com/ninja-af101/AF101.html", "Ninja")
    assert official_store("https://www.apple.com/shop/buy-airpods/airpods-pro-2", "Apple")
    assert not official_store("https://www.crutchfield.com/p_158100XM5B/x.html", "Sony")
    assert not official_store("https://sonyheadphonedeals.example/xm5", "Sony")
    assert not official_store("https://www.bose.com/p/qc-ultra", "Sony")
    # Other subdomains and pages of a maker carry text anyone can write, or no store at all.
    assert not official_store("https://discussions.apple.com/thread/255", "Apple")
    assert not official_store("https://www.apple.com/airpods-pro/", "Apple")
    assert not official_store("https://community.sony.com/s/question/1", "Sony")
    assert not official_store("http://electronics.sony.com/p/wh1000xm5-b", "Sony")
    assert not official_store("https://www.sharkninja.com/x", "Sharky")
    store = offer("Sony WH-1000XM5", url="https://electronics.sony.com/p/wh1000xm5-b").model_copy(
        update={"price": Decimal("228")}
    )
    score = money_score(Decimal("399.99"), [store], False, brand="Sony")
    assert not score.low_confidence and score.best == Decimal("228") and score.value == 30
    other = store.model_copy(update={"url": "https://shop.example/x"})
    assert money_score(Decimal("399.99"), [other], False, brand="Sony").low_confidence


def test_hostile_page_text_is_processed_in_bounded_time():
    import time

    pages = [
        "![" * 200_000,  # open image markup that never closes
        "[" + "a" * 300_000,  # an open link label that never closes
        "[a](" + "b" * 300_000,  # a link target that never closes
        "shipping" + " " * 200_000 + "x",  # whitespace that never reaches a price
        ("Free shipping" + " " * 50 + "$") * 20_000,
    ]
    for raw in pages:
        started = time.perf_counter()
        text = evidence_text("T", "S", raw, SONY)
        assert time.perf_counter() - started < 2.0, raw[:20]
        assert len(text) <= 4000
