"""What the carrier says about a parcel, through a tracking provider.

TRACKING_MODE:
  off        tracking numbers are checked for shape only (see tracking_numbers.py)
  simulator  a clearly labelled stand-in that moves a parcel through the carrier states over time;
             EasyPost's public test codes (EZ1000000001 ... EZ7000000007) give fixed outcomes
  easypost   EasyPost trackers (https://docs.easypost.com/docs/trackers)

Webhooks are only a hint that something changed. The tracker is always re-read from the provider
with our own key before anything is believed, so a forged or replayed webhook cannot mark an order
delivered or release a payout.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import unicodedata
from dataclasses import dataclass, field

import httpx2 as httpx
from sqlalchemy import delete, select

from maxx import schema, storage
from maxx.config import settings

# EasyPost's statuses, which this module uses as its own vocabulary.
STATUSES = {
    "unknown",
    "pre_transit",
    "in_transit",
    "out_for_delivery",
    "available_for_pickup",
    "delivered",
    "return_to_sender",
    "failure",
    "cancelled",
    "error",
}
# The carrier has physically handled the parcel (a label alone is pre_transit).
SCANNED = {"in_transit", "out_for_delivery", "available_for_pickup", "delivered"}
TROUBLE = {"return_to_sender", "failure", "cancelled", "error"}

# EasyPost carrier names for the carriers whose naming is unambiguous; others are auto-detected.
EASYPOST_CARRIER = {"ups": "UPS", "usps": "USPS", "fedex": "FedEx"}

# EasyPost's documented test tracking codes and the state each one simulates.
TEST_CODES = {
    "EZ1000000001": "pre_transit",
    "EZ2000000002": "in_transit",
    "EZ3000000003": "out_for_delivery",
    "EZ4000000004": "delivered",
    "EZ5000000005": "return_to_sender",
    "EZ6000000006": "failure",
    "EZ7000000007": "unknown",
}
_JOURNEY = ["pre_transit", "in_transit", "out_for_delivery", "delivered"]
_MESSAGES = {
    "pre_transit": "Label created; the carrier is waiting for the parcel.",
    "in_transit": "Picked up by the carrier and on its way.",
    "out_for_delivery": "Out for delivery.",
    "delivered": "Delivered.",
    "return_to_sender": "Being returned to the sender.",
    "failure": "The carrier reports a delivery failure.",
    "unknown": "The carrier has no information yet.",
}


class TrackingError(Exception):
    """The provider could not be reached or refused the request. Safe to retry later."""


@dataclass
class TrackerState:
    id: str
    status: str
    detail: str = ""
    estimated_delivery: int | None = None
    destination_country: str = ""
    destination_postal: str = ""
    events: list[dict] = field(default_factory=list)  # {status, message, location, at}
    simulated: bool = False


def enabled() -> bool:
    return settings.tracking_mode in {"simulator", "easypost"}


def is_test_code(number: str) -> bool:
    return number.upper() in TEST_CODES


# ---- simulator ---------------------------------------------------------------------------------


def _sim_read(key: str) -> dict | None:
    with storage.get_store().engine.connect() as db:
        row = db.execute(
            select(schema.simulator_objects.c.document).where(schema.simulator_objects.c.key == key)
        ).first()
    return json.loads(row[0]) if row else None


def _sim_write(key: str, document: dict) -> None:
    with storage.get_store().engine.begin() as db:
        db.execute(delete(schema.simulator_objects).where(schema.simulator_objects.c.key == key))
        db.execute(schema.simulator_objects.insert().values(key=key, document=json.dumps(document)))


def _sim_register(number: str, destination_country: str) -> str:
    tracker_id = f"SIM-TRK-{secrets.token_hex(6).upper()}"
    _sim_write(
        f"trk:{tracker_id}",
        {
            "number": number,
            "created": time.time(),
            "fixed": TEST_CODES.get(number.upper()),
            "destination_country": destination_country,
        },
    )
    return tracker_id


def _sim_state(tracker_id: str) -> TrackerState:
    doc = _sim_read(f"trk:{tracker_id}")
    if doc is None:
        raise TrackingError("Unknown simulated tracker.")
    step = max(1, settings.tracking_sim_step_seconds)
    elapsed = time.time() - doc["created"]
    created = int(doc["created"])
    if doc["fixed"]:
        reached = [doc["fixed"]] if doc["fixed"] == "pre_transit" else ["pre_transit", doc["fixed"]]
    else:
        reached = _JOURNEY[: min(len(_JOURNEY), 1 + int(elapsed // step))]
    events = [
        {
            "status": status,
            "message": _MESSAGES.get(status, status),
            "location": "" if status == "pre_transit" else "Simulated carrier hub",
            "at": created + index * step,
        }
        for index, status in enumerate(reached)
    ]
    status = reached[-1]
    return TrackerState(
        id=tracker_id,
        status=status,
        detail="simulated",
        estimated_delivery=None if status == "delivered" else created + 3 * step,
        destination_country=doc.get("destination_country", ""),
        events=events,
        simulated=True,
    )


# ---- EasyPost ----------------------------------------------------------------------------------


def _easypost() -> httpx.AsyncClient:
    if not settings.easypost_api_key:
        raise TrackingError("TRACKING_MODE=easypost needs EASYPOST_API_KEY.")
    return httpx.AsyncClient(
        base_url=settings.easypost_base_url.rstrip("/"),
        auth=(settings.easypost_api_key, ""),
        timeout=settings.provider_timeout,
        transport=_transport,
    )


_transport = None  # tests inject an httpx MockTransport here


def _epoch(value) -> int | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _from_easypost(body: dict) -> TrackerState:
    status = str(body.get("status") or "unknown")
    if status not in STATUSES:
        status = "unknown"
    events = []
    for item in body.get("tracking_details") or []:
        location = item.get("tracking_location") or {}
        events.append(
            {
                "status": str(item.get("status") or "unknown")[:30],
                "message": str(item.get("message") or "")[:200],
                "location": ", ".join(
                    str(location[k]) for k in ("city", "state", "country") if location.get(k)
                )[:120],
                "at": _epoch(item.get("datetime")) or int(time.time()),
            }
        )
    destination = (body.get("carrier_detail") or {}).get("destination_tracking_location") or {}
    return TrackerState(
        id=str(body.get("id") or ""),
        status=status,
        detail=str(body.get("status_detail") or "")[:60],
        estimated_delivery=_epoch(body.get("est_delivery_date")),
        destination_country=str(destination.get("country") or "")[:2].upper(),
        destination_postal=str(destination.get("zip") or "")[:20],
        events=events,
    )


# ---- interface ---------------------------------------------------------------------------------


async def register(carrier: str, number: str, destination_country: str) -> str | None:
    """Start following a parcel. Returns the provider's tracker id (None when tracking is off)."""
    if settings.tracking_mode == "simulator":
        return _sim_register(number, destination_country)
    if settings.tracking_mode != "easypost":
        return None
    payload: dict = {"tracking_code": number}
    if carrier in EASYPOST_CARRIER:
        payload["carrier"] = EASYPOST_CARRIER[carrier]
    try:
        async with _easypost() as http:
            response = await http.post("/v2/trackers", json={"tracker": payload})
    except httpx.HTTPError as exc:
        raise TrackingError("The tracking provider is unreachable.") from exc
    if response.status_code not in {200, 201}:
        raise TrackingError(f"The tracking provider refused the number ({response.status_code}).")
    return str(response.json().get("id") or "")[:80] or None


async def fetch(tracker_id: str) -> TrackerState:
    if tracker_id.startswith("SIM-TRK-"):
        return _sim_state(tracker_id)
    if settings.tracking_mode != "easypost":
        raise TrackingError("Tracking is not configured.")
    try:
        async with _easypost() as http:
            response = await http.get(f"/v2/trackers/{tracker_id}")
    except httpx.HTTPError as exc:
        raise TrackingError("The tracking provider is unreachable.") from exc
    if response.status_code != 200:
        raise TrackingError(
            f"The tracking provider could not read the tracker ({response.status_code})."
        )
    return _from_easypost(response.json())


def verify_webhook(headers: dict[str, str], body: bytes) -> bool:
    """Check EasyPost's HMAC signature when a webhook secret is configured.

    The signature is HMAC-SHA256 of the raw body with the NFKD-normalised secret, sent as
    `X-Hmac-Signature: hmac-sha256-hex=<hex>` (as in EasyPost's client libraries). Because the
    tracker is re-read from EasyPost anyway, a failure here only refuses the hint.
    """
    secret = settings.easypost_webhook_secret
    if not secret:
        return True
    given = {k.lower(): v for k, v in headers.items()}.get("x-hmac-signature", "")
    key = unicodedata.normalize("NFKD", secret).encode()
    expected = "hmac-sha256-hex=" + hmac.new(key, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given, expected)


def tracker_id_from_webhook(body: bytes) -> str | None:
    try:
        event = json.loads(body)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("description") not in {
        "tracker.updated",
        "tracker.created",
    }:
        return None
    result = event.get("result") or {}
    value = str(result.get("id") or "") if isinstance(result, dict) else ""
    return value[:80] or None
