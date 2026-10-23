"""At-rest encryption for secrets kept in the database (TOTP seeds).

AES-256-GCM with a per-purpose key derived from the master key, so a ciphertext made for one purpose
cannot be replayed into another. The master key comes from SECRET_KEY; in development it is created
once, with owner-only permissions, in .local/secret_key so restarts keep working.
"""

from __future__ import annotations

import base64
import os
import secrets as stdlib_secrets
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from maxx.config import ROOT, settings

MIN_KEY_LENGTH = 32


class SecretKeyError(RuntimeError):
    pass


@lru_cache
def _master_key() -> bytes:
    value = settings.secret_key.strip()
    if value:
        if len(value) < MIN_KEY_LENGTH:
            raise SecretKeyError(f"SECRET_KEY must be at least {MIN_KEY_LENGTH} characters.")
        return value.encode()
    if settings.environment == "production":
        raise SecretKeyError("SECRET_KEY is required in production.")
    path = ROOT / ".local" / "secret_key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(stdlib_secrets.token_urlsafe(48))
    return path.read_text().strip().encode()


def reset() -> None:
    _master_key.cache_clear()


def _key(purpose: str) -> bytes:
    return HKDF(hashes.SHA256(), 32, salt=None, info=f"maxx:{purpose}".encode()).derive(
        _master_key()
    )


def encrypt(plaintext: str, purpose: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key(purpose)).encrypt(nonce, plaintext.encode(), purpose.encode())
    return base64.urlsafe_b64encode(nonce + sealed).decode()


def decrypt(token: str, purpose: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode())
    return AESGCM(_key(purpose)).decrypt(raw[:12], raw[12:], purpose.encode()).decode()
