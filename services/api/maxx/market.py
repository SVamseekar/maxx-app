"""Trusted delivered-price median and demand reasoning; no seller state inputs."""

from decimal import Decimal

from maxx.scan import PriceRow


def target_price(rows):
    hosts = set()
    from urllib.parse import urlparse

    values = []
    for row in rows:
        host = urlparse(str(row.url)).hostname
        if row.same_item and row.in_stock and row.shipping is not None and host not in hosts:
            hosts.add(host)
            values.append(row.price + row.shipping)
    if len(values) < 2:
        return None
    values.sort()
    middle = len(values) // 2
    return (
        values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    ).quantize(Decimal(".01"))


def apply_market(bloc, rows, mode, checked_at):
    bloc.market_rows = rows
    bloc.market_mode = mode
    bloc.market_checked_at = checked_at
    bloc.market_expires_at = checked_at + 21600
    bloc.target_price = target_price(rows)


def fixture_rows(title, typical):
    # Clearly simulated historical-price evidence for judge seeds; never a live fallback.
    return [
        PriceRow(
            title=title,
            url=f"https://fixture{i}.example/price-history",
            price=(typical * factor).quantize(Decimal(".01")),
            shipping="0",
            same_item=True,
            in_stock=True,
            evidence="Simulated fixture price history, not a merchant quote.",
        )
        for i, factor in enumerate([Decimal(".7"), Decimal(".8")])
    ]


async def refresh_market(bloc, mode, calls):
    import time

    import httpx2 as httpx

    from maxx import storage
    from maxx.config import settings
    from maxx.flow import comparable_prices, price_cache_key
    from maxx.providers import ProviderError
    from maxx.scan import Item

    if mode == "fixture":
        apply_market(
            bloc, fixture_rows(bloc.title, bloc.typical_price), "fixture", int(time.time())
        )
        return
    if not settings.tavily_api_key or not settings.nebius_api_key:
        raise ProviderError("Live Bloc pricing requires server-side Tavily and Nebius keys.")
    item = Item(title=bloc.title, price=bloc.typical_price, currency="USD")
    async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
        rows = await comparable_prices(client, item, bloc.id, calls, history=True)
    apply_market(bloc, rows, "live", int(time.time()))
    bloc.market_expires_at = storage.get_store().cache_expiry(
        price_cache_key(item, history=True)
    ) or int(time.time())
