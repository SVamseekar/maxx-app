"""Minimal JOSE helpers for OpenID Connect: RS256 verification and ES256 signing.

Only what sign-in needs. The algorithm is never taken from the token: verification is RS256 only,
so "alg: none" and HMAC-confusion tokens are rejected before any key is touched.
"""

from __future__ import annotations

import base64
import json
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class TokenError(Exception):
    """The token is malformed, unsigned, expired or addressed to someone else."""


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def split(token: str) -> tuple[dict, dict, bytes, bytes]:
    """Return (header, claims, signing_input, signature) without trusting any of it yet."""
    try:
        head, body, sig = token.split(".")
        header, claims = json.loads(b64url_decode(head)), json.loads(b64url_decode(body))
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise ValueError
        return header, claims, f"{head}.{body}".encode("ascii"), b64url_decode(sig)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise TokenError("The identity token is malformed.") from exc


def verify_rs256(token: str, jwks: dict) -> dict:
    """Verify the signature against a JWKS and return the claims."""
    header, claims, signing_input, signature = split(token)
    if header.get("alg") != "RS256":
        raise TokenError("The identity token uses an unsupported signature algorithm.")
    key = next(
        (
            k
            for k in jwks.get("keys", [])
            if k.get("kid") == header.get("kid") and k.get("kty") == "RSA"
        ),
        None,
    )
    if key is None:
        raise TokenError("The identity token was signed by an unknown key.")
    try:
        public = rsa.RSAPublicNumbers(
            int.from_bytes(b64url_decode(key["e"]), "big"),
            int.from_bytes(b64url_decode(key["n"]), "big"),
        ).public_key()
        public.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, KeyError, ValueError) as exc:
        raise TokenError("The identity token signature is invalid.") from exc
    return claims


def check_claims(claims: dict, *, issuers: set[str], audience: str, nonce: str | None) -> None:
    """OpenID Connect Core 3.1.3.7 checks that apply to a code-flow ID token."""
    now = time.time()
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if claims.get("iss") not in issuers:
        raise TokenError("The identity token came from an unexpected issuer.")
    if audience not in audiences:
        raise TokenError("The identity token was issued for a different application.")
    expires = claims.get("exp")
    if not isinstance(expires, int | float) or expires < now - 60:
        raise TokenError("The identity token has expired.")
    issued = claims.get("iat")
    if isinstance(issued, int | float) and issued > now + 300:
        raise TokenError("The identity token is not valid yet.")
    if nonce is not None and claims.get("nonce") != nonce:
        raise TokenError("The identity token does not match this sign-in attempt.")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise TokenError("The identity token has no subject.")


def sign_es256(claims: dict, key_pem: str, key_id: str) -> str:
    """Compact JWS signed with a P-256 private key (Apple client secrets)."""
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("Apple's key must be an ECDSA P-256 private key.")
    head = b64url_encode(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    body = b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    der = key.sign(f"{head}.{body}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"{head}.{body}.{b64url_encode(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
