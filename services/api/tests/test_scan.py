import io
from decimal import Decimal

from fastapi.testclient import TestClient
from PIL import Image

from maxx.main import app
from maxx.scan import Item, PriceRow, money_score, validate_image


def png():
    stream = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_score_decimal_shipping_and_excluded_rows():
    rows = [
        PriceRow(
            title="A",
            url="https://shop.example/a",
            price="70",
            shipping="10",
            same_item=True,
            in_stock=True,
        ),
        PriceRow(
            title="B",
            url="https://shop.example/b",
            price="85",
            shipping="0",
            same_item=True,
            in_stock=True,
        ),
        PriceRow(
            title="C",
            url="https://shop.example/c",
            price="1",
            shipping="0",
            same_item=False,
            in_stock=True,
        ),
    ]
    score = money_score(Decimal("100"), rows, False)
    assert score.value == 65
    assert score.best == Decimal("80")
    assert not score.low_confidence
    assert money_score(Decimal("100"), rows, True).value == 50
    assert money_score(Decimal("200"), rows, False).value == 30
    assert money_score(None, rows, False).value is None
    assert money_score(Decimal("100"), [], False).value is None


def test_null_fields_and_non_positive_prices():
    assert Item(title=None, price=None).price is None
    import pytest

    with pytest.raises(ValueError):
        Item(title="A", price="0")


def test_image_validation():
    import pytest

    assert validate_image(png(), "image/png") == "image/png"
    for data, mime in [(b"fake", "image/png"), (png(), "image/jpeg"), (png(), "image/svg+xml")]:
        with pytest.raises(ValueError):
            validate_image(data, mime)
    with pytest.raises(ValueError):
        validate_image(b"x" * (8 * 1024 * 1024 + 1), "image/png")


def test_upload_errors_and_missing_configuration(monkeypatch):
    from maxx.config import settings

    monkeypatch.setattr(settings, "scan_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    client = TestClient(app)
    assert (
        client.post("/scan", content=b"bad", headers={"content-type": "image/png"}).status_code
        == 422
    )
    result = client.post("/scan", content=png(), headers={"content-type": "image/png"})
    assert result.status_code == 503
    assert "key" not in result.text.lower() or "configure" in result.text.lower()


def test_fixture_end_to_end(monkeypatch):
    import json

    from maxx.config import ROOT, settings

    monkeypatch.setattr(settings, "scan_mode", "fixture")
    cases = json.loads((ROOT / "evals/fixtures.json").read_text())
    client = TestClient(app)
    for case in cases:
        image = (ROOT / "evals" / case["file"]).read_bytes()
        response = client.post("/scan", content=image, headers={"content-type": "image/png"})
        assert response.status_code == 200
        result = response.json()
        assert result["mode"] == "fixture"
        assert result["item"] == case["item"]
        assert result["calls"] == []
        if case["name"] in ["unreadable", "non-usd"]:
            assert result["score"]["value"] is None
            assert result["recommendation"]["primary"] == "WAIT"
        else:
            assert result["recommendation"]["primary"] == "CHEAPER"
    result = client.post("/scan", content=png(), headers={"content-type": "image/png"})
    assert result.status_code == 503
    assert "supplied sample" in result.json()["message"]


def test_grounding_rejects_invented_prices_stock_and_shipping():
    from maxx.flow import ground_rows

    source = {
        "url": "https://shop.example/a",
        "content": "New headphone USD $90.00. Shipping calculated later.",
    }
    invented = PriceRow(
        title="A",
        url=source["url"],
        price="1",
        shipping="0",
        same_item=True,
        in_stock=True,
        evidence=source["content"],
    )
    assert ground_rows([invented], [source]) == []
    valid = invented.model_copy(update={"price": Decimal("90")})
    grounded = ground_rows([valid], [source])
    assert grounded[0].shipping is None
    assert not grounded[0].in_stock
    assert money_score(Decimal("100"), grounded, False).value is None


def test_live_transport_schema_retry_and_logging(monkeypatch, tmp_path):
    import json

    import httpx2 as httpx

    from maxx import flow
    from maxx.config import settings

    monkeypatch.setattr(settings, "scan_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "private-nebius-key")
    monkeypatch.setattr(settings, "tavily_api_key", "private-tavily-key")
    vision = Item(
        title="Sony WH-1000XM5 Black",
        brand="Sony",
        model="WH-1000XM5",
        variant="Black",
        price="100.00",
        currency="USD",
        merchant="Store",
        visible_text="Sony WH-1000XM5 Black $100.00",
    )
    evidence = "Sony WH-1000XM5 Black $80.00 In stock. Free shipping."
    sources = [{"url": f"https://shop{i}.example/product", "content": evidence} for i in range(2)]
    attempt = 0

    def transport(req):
        nonlocal attempt
        assert req.headers["authorization"].startswith("Bearer private-")
        if req.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": m}
                        for m in [settings.model_vision, settings.model_fast, settings.model_reason]
                    ]
                },
            )
        body = json.loads(req.content)
        if req.url.host == "api.tavily.com":
            assert body["max_results"] == 8
            return httpx.Response(200, json={"results": sources})
        if body["model"] == settings.model_vision:
            assert body["messages"][1]["content"][1]["image_url"]["url"].startswith(
                "data:image/png;base64,"
            )
            attempt += 1
            content = "not json" if attempt == 1 else vision.model_dump_json()
        elif body["model"] == settings.model_fast:
            if "sources" in json.loads(body["messages"][1]["content"][0]["text"]).get("data", {}):
                content = json.dumps(
                    {
                        "rows": [
                            {
                                "title": vision.title,
                                "url": s["url"],
                                "price": "80.00",
                                "shipping": "0",
                                "in_stock": True,
                                "same_item": True,
                                "evidence": evidence,
                            }
                            for s in sources
                        ]
                    }
                )
            else:
                content = vision.model_dump_json(include={"brand", "model", "variant"})
        else:
            # Hallucinated numbers must trigger the safe template.
            content = json.dumps(
                {"primary": "CHEAPER", "headline": "Save $999!", "explanation": "Invented saving."}
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        flow.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(transport), **kw),
    )
    result = TestClient(app).post("/scan", content=png(), headers={"content-type": "image/png"})
    assert result.status_code == 200
    result = result.json()
    assert result["mode"] == "live"
    assert result["score"]["value"] == 65
    assert "$20.00" in result["recommendation"]["explanation"]
    assert len(result["calls"]) == 7
    assert attempt == 2

    from maxx import storage

    logs = str(storage.get_store().recent_calls())
    assert "private-nebius-key" not in logs
    assert "base64" not in logs
    assert "prompt_tokens" in logs


def test_provider_timeout_is_safe(monkeypatch, tmp_path):
    import httpx2 as httpx

    from maxx import flow
    from maxx.config import settings

    monkeypatch.setattr(settings, "scan_mode", "live")
    monkeypatch.setattr(settings, "nebius_api_key", "secret")
    monkeypatch.setattr(settings, "tavily_api_key", "secret")

    def timeout(req):
        raise httpx.ReadTimeout("secret provider body", request=req)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        flow.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(timeout), **kw),
    )
    response = TestClient(app).post("/scan", content=png(), headers={"content-type": "image/png"})
    assert response.status_code == 503
    assert "timed out" in response.text
    assert "secret" not in response.text


def test_tavily_extract_and_cache(monkeypatch, tmp_path):
    import asyncio

    import httpx2 as httpx

    from maxx import flow

    requested = []
    source_url = "https://shop.example/product"
    evidence = "Sony WH-1000XM5 Black $80.00 In stock. Free shipping."

    def transport(req):
        import json

        requested.append(req.url.path)
        if req.url.path == "/search":
            return httpx.Response(
                200, json={"results": [{"url": source_url, "content": "Click to see price"}]}
            )
        if req.url.path == "/extract":
            assert json.loads(req.content)["urls"] == [source_url]
            return httpx.Response(
                200, json={"results": [{"url": source_url, "raw_content": evidence}]}
            )
        rows = {
            "rows": [
                {
                    "title": "Sony WH-1000XM5 Black",
                    "url": source_url,
                    "price": "80.00",
                    "shipping": "0",
                    "same_item": True,
                    "in_stock": True,
                    "evidence": evidence,
                }
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(rows)}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            item = Item(title="Sony WH-1000XM5 Black", price="100", currency="USD")
            calls = []
            rows = await flow.comparable_prices(client, item, "test", calls)
            assert rows[0].price == Decimal("80")
            assert len(calls) == 3
            cached = await flow.comparable_prices(client, item, "test", calls)
            assert cached == rows
            assert calls[-1]["status"] == "cache"

    asyncio.run(run())
    assert requested == ["/search", "/extract", "/v1/chat/completions"]


def test_non_usd_comparable_excluded():
    from maxx.flow import ground_rows

    source = {
        "url": "https://shop.example/a",
        "content": "Sony WH-1000XM5 CAD $90.00 In stock. Free shipping.",
    }
    row = PriceRow(
        title="Sony WH-1000XM5",
        url=source["url"],
        price="90",
        shipping="0",
        same_item=True,
        in_stock=True,
        evidence=source["content"],
    )
    assert not ground_rows([row], [source])[0].same_item


def test_verification_probe_does_not_pass_without_key(monkeypatch, capsys):
    import asyncio

    import pytest

    from maxx.config import settings
    from maxx.verify_providers import main

    monkeypatch.setattr(settings, "nebius_api_key", "")
    with pytest.raises(SystemExit) as exc:
        asyncio.run(main())
    assert exc.value.code == 2
    assert "unverified" in capsys.readouterr().out


def test_edited_fixture_product_discards_old_comparables(monkeypatch):
    import json

    from maxx.config import ROOT, settings

    monkeypatch.setattr(settings, "scan_mode", "fixture")
    case = json.loads((ROOT / "evals/fixtures.json").read_text())[0]
    response = TestClient(app).post(
        "/scan?title=Different%20product&price=50",
        content=(ROOT / "evals" / case["file"]).read_bytes(),
        headers={"content-type": "image/png"},
    )
    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert response.json()["score"]["value"] is None


def test_expired_durable_price_cache_refetches_provider_and_is_not_mutable():
    import asyncio
    import json
    import time

    import httpx2 as httpx

    from maxx import flow, storage

    seen = []
    evidence = "Sony WH-1000XM5 Black $80.00 In stock. Free shipping."
    row = {
        "title": "Sony WH-1000XM5 Black",
        "url": "https://shop.example/item",
        "price": "80",
        "shipping": "0",
        "same_item": True,
        "in_stock": True,
        "evidence": evidence,
    }

    def transport(req):
        seen.append(req.url.path)
        if req.url.path == "/search":
            return httpx.Response(200, json={"results": [{"url": row["url"], "content": evidence}]})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"rows": [row]})}}]}
        )

    async def run():
        item = Item(title="Sony WH-1000XM5 Black", currency="USD", price="100")
        key = flow.price_cache_key(item)
        store = storage.get_store()
        store.cache_put(key, [row], now=int(time.time()) - 21600)
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            result = await flow.comparable_prices(client, item, "expiry", [])
            assert seen == ["/search", "/v1/chat/completions"]
            result[0].price = Decimal("1")
            cached = await flow.comparable_prices(client, item, "hit", [])
            assert cached[0].price == Decimal("80")
            assert len(seen) == 2

    asyncio.run(run())
