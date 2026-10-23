"""Optional Cloudflare Turnstile challenge for sign-up, recovery and repeated failed sign-ins."""

from __future__ import annotations

import httpx2 as httpx

from maxx.config import settings

transport: httpx.AsyncBaseTransport | None = None


def enabled() -> bool:
    return bool(settings.turnstile_site_key and settings.turnstile_secret)


async def verify(token: str | None, ip: str) -> bool:
    """Check a one-use token with Cloudflare. A missing or rejected token is a failure."""
    if not enabled():
        return True
    if not token or len(token) > 2048:
        return False
    try:
        async with httpx.AsyncClient(transport=transport, timeout=5) as client:
            response = await client.post(
                settings.turnstile_verify_url,
                data={"secret": settings.turnstile_secret, "response": token, "remoteip": ip},
            )
        return response.status_code == 200 and response.json().get("success") is True
    except (httpx.HTTPError, ValueError):
        return False  # fail closed: a challenge that cannot be checked is not passed
