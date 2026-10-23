"""Seller identity checks through a verification provider.

VERIFY_MODE:
  off        no identity check (only when SELLER_IDENTITY_REQUIRED is false)
  simulator  a clearly labelled stand-in page that lets the seller pass or fail the check
  stripe     Stripe Identity: a government ID document plus a matching live selfie
             (https://docs.stripe.com/identity/verification-sessions)

The seller is sent to the provider's own page, so Maxx never sees or stores the document or the
selfie. Maxx keeps only the outcome, the verified name and the document's country. Results arrive
asynchronously: the provider's webhook is checked for its signature and then, as with tracking,
the session is read back from the provider with Maxx's own key before anything is believed. The
seller returning to Maxx after the check proves nothing on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

import httpx2 as httpx
from sqlalchemy import delete, select

from maxx import schema, storage
from maxx.config import settings

TOLERANCE = 300  # seconds a signed webhook stays acceptable (Stripe's own default)


class IdentityError(Exception):
    """The provider could not be reached or refused. Safe to retry."""


@dataclass
class Result:
    session_id: str
    status: str  # pending | verified | requires_input | canceled
    first_name: str = ""
    last_name: str = ""
    country: str = ""
    simulated: bool = False

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def required() -> bool:
    return settings.seller_identity_required and settings.verify_mode in {"simulator", "stripe"}


# ---- simulator ---------------------------------------------------------------------------------


def _sim_key(session_id: str) -> str:
    return f"idv:{session_id}"


def _sim_read(session_id: str) -> dict | None:
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.simulator_objects.c.document).where(
                schema.simulator_objects.c.key == _sim_key(session_id)
            )
        ).first()
    return json.loads(row[0]) if row else None


def _sim_write(session_id: str, document: dict) -> None:
    with storage.get_store().engine.begin() as db:
        db.execute(
            delete(schema.simulator_objects).where(
                schema.simulator_objects.c.key == _sim_key(session_id)
            )
        )
        db.execute(
            schema.simulator_objects.insert().values(
                key=_sim_key(session_id), document=json.dumps(document)
            )
        )


def simulate_outcome(session_id: str, seller_id: str, verified: bool, name: str) -> None:
    """The seller's click on the simulated verification page."""
    doc = _sim_read(session_id)
    if not doc or doc["seller_id"] != seller_id or doc["status"] != "pending":
        raise IdentityError("This simulated check is not open.")
    first, _, last = name.strip().partition(" ")
    doc.update(
        status="verified" if verified else "requires_input",
        first_name=first[:80],
        last_name=last[:80],
    )
    _sim_write(session_id, doc)


# ---- Stripe ------------------------------------------------------------------------------------

_transport = None  # tests inject an httpx MockTransport here


def _stripe() -> httpx.AsyncClient:
    if not settings.stripe_secret_key:
        raise IdentityError("VERIFY_MODE=stripe needs STRIPE_SECRET_KEY.")
    return httpx.AsyncClient(
        base_url=settings.stripe_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
        timeout=settings.provider_timeout,
        transport=_transport,
    )


STATUS = {
    "verified": "verified",
    "requires_input": "requires_input",
    "processing": "pending",
    "canceled": "canceled",
}


# ---- interface ---------------------------------------------------------------------------------


async def start(seller: dict) -> tuple[str, str]:
    """Open a verification session. Returns (session id, URL to send the seller to).

    The URL is single-use and short-lived; it is handed to the seller and never stored.
    """
    if settings.verify_mode == "simulator":
        session_id = f"SIM-IDV-{secrets.token_hex(8).upper()}"
        _sim_write(
            session_id,
            {
                "seller_id": seller["id"],
                "status": "pending",
                "created": int(time.time()),
                "country": seller["country"],
            },
        )
        return session_id, f"/sell/verify-identity?session={session_id}"
    if settings.verify_mode != "stripe":
        raise IdentityError("Identity checks are not configured.")
    form = {
        "type": "document",
        "options[document][require_matching_selfie]": "true",
        "options[document][require_live_capture]": "true",
        "client_reference_id": seller["id"],
        "metadata[seller_code]": seller["code"],
        "return_url": settings.public_base_url.rstrip("/") + "/sell?identity=returned",
    }
    try:
        async with _stripe() as http:
            response = await http.post(
                "/v1/identity/verification_sessions",
                data=form,
                headers={"Idempotency-Key": f"idv-{seller['id']}-{int(time.time() // 600)}"},
            )
    except httpx.HTTPError as exc:
        raise IdentityError("The identity provider is unreachable.") from exc
    if response.status_code != 200:
        raise IdentityError(f"The identity provider refused ({response.status_code}).")
    body = response.json()
    return str(body["id"]), str(body["url"])


async def fetch(session_id: str) -> Result:
    if session_id.startswith("SIM-IDV-"):
        doc = _sim_read(session_id)
        if doc is None:
            raise IdentityError("Unknown simulated session.")
        return Result(
            session_id,
            doc["status"],
            doc.get("first_name", ""),
            doc.get("last_name", ""),
            doc.get("country", ""),
            simulated=True,
        )
    if settings.verify_mode != "stripe":
        raise IdentityError("Identity checks are not configured.")
    try:
        async with _stripe() as http:
            response = await http.get(
                f"/v1/identity/verification_sessions/{session_id}",
                params={"expand[]": "verified_outputs"},
            )
    except httpx.HTTPError as exc:
        raise IdentityError("The identity provider is unreachable.") from exc
    if response.status_code != 200:
        raise IdentityError(f"The identity provider could not read it ({response.status_code}).")
    body = response.json()
    outputs = body.get("verified_outputs") or {}
    address = outputs.get("address") or {}
    return Result(
        session_id,
        STATUS.get(str(body.get("status")), "pending"),
        str(outputs.get("first_name") or "")[:80],
        str(outputs.get("last_name") or "")[:80],
        str(address.get("country") or "")[:2].upper(),
    )


def verify_webhook(header: str, body: bytes, now: float | None = None) -> bool:
    """Check a `Stripe-Signature` header: t=<timestamp>,v1=<hex HMAC-SHA256 of "t.body">."""
    secret = settings.stripe_webhook_secret
    if not secret or not header:
        return False
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        stamp = int(parts.get("t", ["0"])[0])
    except ValueError:
        return False
    if abs((now or time.time()) - stamp) > TOLERANCE:
        return False
    signed = f"{stamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, given) for given in parts.get("v1", []))


def session_from_webhook(body: bytes) -> str | None:
    try:
        event = json.loads(body)
    except ValueError:
        return None
    if not isinstance(event, dict) or not str(event.get("type", "")).startswith(
        "identity.verification_session."
    ):
        return None
    obj = (event.get("data") or {}).get("object") or {}
    value = str(obj.get("id") or "") if isinstance(obj, dict) else ""
    return value[:80] or None
