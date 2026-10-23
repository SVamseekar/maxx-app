"""Breached-password screening through Have I Been Pwned's k-anonymity range API.

Only the first five characters of the password's SHA-1 leave the server, and `Add-Padding` hides
the size of the answer. A matching hash means the password is in public breach data and attackers
try it first. If the service is unreachable the check is skipped (and logged) rather than blocking
people from signing up.
"""

from __future__ import annotations

import hashlib
import logging

import httpx2 as httpx

from maxx.config import settings

log = logging.getLogger(__name__)
transport: httpx.AsyncBaseTransport | None = None


async def times_breached(password: str) -> int | None:
    """How often the password appears in breach data, or None when the check could not run."""
    if not settings.hibp_enabled:
        return None
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(transport=transport, timeout=3) as client:
            response = await client.get(
                settings.hibp_url + prefix,
                headers={"Add-Padding": "true", "User-Agent": "Maxx-password-check"},
            )
        if response.status_code != 200:
            raise httpx.HTTPError("unexpected status")
    except httpx.HTTPError:
        log.warning("Breached-password check unavailable; continuing without it.")
        return None
    for line in response.text.splitlines():
        found, _, count = line.partition(":")
        if found.strip().upper() == suffix:
            return int(count) if count.strip().isdigit() else 1
    return 0


async def is_breached(password: str) -> bool:
    count = await times_breached(password)
    return bool(count)
