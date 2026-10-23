"""Time-based one-time passwords (RFC 6238) and single-use recovery codes. Standard library only."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1  # accept the previous and next 30-second window for clock skew
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (i, l, o, 0, 1)


def new_seed() -> str:
    """160-bit seed, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(seed: str, step: int) -> str:
    key = base64.b32decode(seed + "=" * (-len(seed) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def match(seed: str, code: str, now: float | None = None) -> int | None:
    """Return the time step the code belongs to, or None. Compares every window in constant time."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    center, found = current_step(now), None
    for step in range(center - DRIFT_STEPS, center + DRIFT_STEPS + 1):
        if hmac.compare_digest(_code(seed, step), code):
            found = step
    return found


def code_at(seed: str, now: float | None = None) -> str:
    return _code(seed, current_step(now))


def otpauth_uri(seed: str, account: str, issuer: str = "Maxx") -> str:
    label = f"{quote(issuer)}:{quote(account)}"
    return (
        f"otpauth://totp/{label}?secret={seed}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def new_recovery_codes(count: int = 10) -> list[str]:
    """Ten single-use codes like `k3m9x-7qpv2` (about 50 bits each)."""
    return [
        "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(5))
        + "-"
        + "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(5))
        for _ in range(count)
    ]


def normalize_recovery(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def recovery_hash(code: str) -> str:
    return hashlib.sha256(("maxx-recovery:" + normalize_recovery(code)).encode()).hexdigest()


def looks_like_recovery(code: str) -> bool:
    cleaned = normalize_recovery(code)
    return len(cleaned) == 10 and not cleaned.isdigit()
