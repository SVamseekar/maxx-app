"""Credential primitives: password hashing, token digests and input policy (standard library)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

# scrypt: memory-hard, in the standard library. 2**15 * 8 * 128 bytes = 32 MiB per hash.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD, MAX_PASSWORD = 10, 128

EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

COMMON_PASSWORDS = {
    "password",
    "password1",
    "password12",
    "password123",
    "1234567890",
    "12345678910",
    "qwertyuiop",
    "qwerty12345",
    "iloveyou12",
    "letmein123",
    "welcome123",
    "admin12345",
    "abc1234567",
    "1q2w3e4r5t",
    "passw0rd12",
    "football12",
    "baseball12",
    "monkey1234",
    "dragon1234",
    "superman12",
    "trustno1234",
    "changeme123",
    "maxx1234567",
    "maxxmaxxmaxx",
}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. Always spends a hash's worth of time, even for unknown accounts."""
    if not stored:
        hashlib.scrypt(
            b"x", salt=b"0" * 16, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM
        )
        return False
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=SCRYPT_MAXMEM,
            dklen=len(base64.b64decode(expected)),
        )
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def valid_email(value: str) -> bool:
    return len(value) <= 254 and bool(EMAIL.match(value))


def password_problem(password: str, email: str = "", display_name: str = "") -> str | None:
    """Return a human-readable reason a password is rejected, or None if it is acceptable."""
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Use at most {MAX_PASSWORD} characters."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        return "That password is too easy to guess. Try a longer phrase."
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and lowered == local:
        return "Your password cannot be your email name."
    if display_name and len(display_name) >= 4 and lowered == display_name.lower():
        return "Your password cannot be your name."
    return None


def clean_display_name(value: str, fallback_email: str = "") -> str:
    name = " ".join(value.split())[:80]
    if name:
        return name
    return (fallback_email.split("@")[0] or "Maxx buyer")[:80]


def safe_next(value: str | None, default: str = "/") -> str:
    """Only same-site relative paths survive; everything else, including //host, becomes default."""
    if not value or len(value) > 300 or not value.startswith("/"):
        return default
    if value.startswith("//") or "\\" in value or any(ord(c) < 32 for c in value):
        return default
    return value
