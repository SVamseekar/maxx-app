import asyncio
import json
from decimal import Decimal

import httpx2 as httpx
from fastapi.testclient import TestClient

from maxx import flow
from maxx.main import app
from maxx.price_search import (
    blocked_page,
    extract_payload,
    extract_targets,
    search_payload,
    search_query,
    sells_items,
    variant_conflict,
)
from maxx.scan import Item, PriceRow

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


def test_the_query_names_each_word_once_and_the_search_skips_sites_that_do_not_sell():
    assert search_query(SONY) == (
        "Sony WH-1000XM5 Black Wireless Noise Canceling Headphones price buy new"
    )
    payload = search_payload(SONY)
    assert payload["country"] == "united states"
    assert payload["search_depth"] == "basic" and payload["chunks_per_source"] == 3
    assert "investing.com" in payload["exclude_domains"]
    assert "camelcamelcamel.com" in payload["exclude_domains"]
    assert "camelcamelcamel.com" not in search_payload(SONY, history=True)["exclude_domains"]


def test_excluded_sites_are_dropped_with_their_subdomains():
    assert not sells_items("https://ca.investing.com/news/sony")
    assert not sells_items("https://en.wikipedia.org/wiki/Sony")
    assert sells_items("https://electronics.sony.com/audio/headphones")
    assert not sells_items("https://camelcamelcamel.com/product/B09XS7JWHH")
    assert sells_items("https://camelcamelcamel.com/product/B09XS7JWHH", history=True)


def test_pages_without_a_price_are_read_first_then_pages_missing_stock_or_shipping():
    sources = [
        {"url": "https://a.example", "content": "$348.00 In stock. Free shipping."},
        {"url": "https://b.example", "content": "$349.99 Add to cart"},
        {"url": "https://c.example", "content": "See price in cart"},
    ]
    assert extract_targets(sources) == ["https://b.example", "https://c.example"]
    walled = [{"url": "https://www.amazon.com/dp/B09XS7JWHH", "content": "See price"}]
    assert extract_targets(walled + sources[1:]) == ["https://b.example", "https://c.example"]
    payload = extract_payload(SONY, ["https://c.example"])
    assert payload["extract_depth"] == "advanced" and payload["chunks_per_source"] == 3
    assert payload["query"].endswith("shipping in stock")


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


def test_a_renewed_offer_elsewhere_on_the_page_does_not_reject_this_offer():
    page = (
        "Sony WH-1000XM5 Black $348.00 In stock. Free shipping. "
        + "Specs and reviews. " * 40
        + "Also available: Renewed from $229.00"
    )
    source = {"url": "https://shop.example/x", "content": page}
    row = offer("Sony WH-1000XM5 Black", evidence="Sony WH-1000XM5 Black $348.00 In stock.")
    assert flow.ground_rows([row], [source])[0].same_item
    renewed = {"url": source["url"], "content": "Renewed: Sony WH-1000XM5 Black $348.00 In stock."}
    assert not flow.ground_rows([row.model_copy()], [renewed])[0].same_item


def test_the_search_drops_news_ignores_blocked_pages_and_vetoes_other_models():
    sent = {}
    shop, news, blocked = (
        "https://shop.example/xm5",
        "https://www.businessinsider.com/sony-review",
        "https://bigstore.example/p/1",
    )

    def transport(req):
        body = json.loads(req.content)
        sent[req.url.path] = body
        if req.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": shop,
                            "title": "Sony WH-1000XM5",
                            "content": "Sony WH-1000XM5 Black",
                        },
                        {"url": news, "title": "Review", "content": "Sony XM5 now $298"},
                        {"url": blocked, "title": "Big Store", "content": "Sony WH-1000XM5"},
                    ]
                },
            )
        if req.url.path == "/extract":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": shop,
                            "raw_content": "Sony WH-1000XM5 Black $348.00 In stock. Free shipping.",
                        },
                        {
                            "url": blocked,
                            "raw_content": "Robot Check. Type the characters you see.",
                        },
                    ],
                    "failed_results": [],
                },
            )
        rows = [
            offer(
                "Sony WH-1000XM5 Black", "Sony WH-1000XM5 Black $348.00 In stock.", shop
            ).model_dump(mode="json"),
            offer(
                "Sony WH-1000XM4 Black", "Sony WH-1000XM5 Black $348.00 In stock.", blocked
            ).model_dump(mode="json"),
        ]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"rows": rows})}}]}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            return await flow.comparable_prices(client, SONY, "test-search", [])

    rows = asyncio.run(run())
    assert sent["/search"]["exclude_domains"] and sent["/search"]["country"] == "united states"
    assert sent["/extract"]["urls"] == [shop, blocked]
    assert [r.url.host for r in rows] == ["shop.example"]
    assert rows[0].same_item and rows[0].price == Decimal("348")


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


def test_a_slow_page_read_falls_back_to_the_search_snippets():
    shop = "https://shop.example/xm5"
    evidence = "Sony WH-1000XM5 Black $348.00 Free shipping."

    def transport(req):
        if req.url.path == "/search":
            # Stock is not in the snippet, so the page is read in full, and that read times out.
            return httpx.Response(200, json={"results": [{"url": shop, "content": evidence}]})
        if req.url.path == "/extract":
            raise httpx.ReadTimeout("slow page", request=req)
        row = offer("Sony WH-1000XM5 Black", evidence, shop).model_dump(mode="json")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"rows": [row]})}}]}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            calls = []
            return await flow.comparable_prices(client, SONY, "test-slow", calls), calls

    rows, calls = asyncio.run(run())
    assert [(c["provider"], c["purpose"]) for c in calls] == [
        ("tavily", "search"),
        ("tavily", "extract"),
        ("nebius", "extract"),
    ]
    assert calls[1]["status"] != "ok"
    assert rows[0].price == Decimal("348") and rows[0].shipping == 0 and not rows[0].in_stock


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
