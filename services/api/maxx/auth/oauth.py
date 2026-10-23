"""OAuth 2.0 / OpenID Connect sign-in for Google, Apple, Microsoft and GitHub.

Hardening that applies to every provider (RFC 9700, OAuth 2.0 Security BCP):
- authorization code flow with PKCE (S256) and a server-side, browser-bound `state`;
- one exact redirect URI per provider, so a response meant for one provider is never accepted
  as another's (mix-up defence);
- OpenID providers also get a `nonce`, and the ID token's signature (RS256, against the
  provider's published keys), issuer, audience, expiry and nonce are checked before any claim
  is believed;
- an email address is only ever reported as verified when the provider itself proved it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx2 as httpx

from maxx.auth import jwtutil, store
from maxx.auth.security import new_token
from maxx.config import settings

MICROSOFT_PERSONAL_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
APPLE_ISSUER = "https://appleid.apple.com"


class OAuthError(Exception):
    """Safe to show to the person signing in; never contains provider tokens or secrets."""


@dataclass(frozen=True)
class Profile:
    subject: str
    email: str | None
    email_verified: bool
    name: str
    avatar_url: str | None


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    authorize_url: str
    token_url: str
    scope: str
    client_id: str
    client_secret: Callable[[], str] = field(default=lambda: "")
    configured: bool = False
    oidc: bool = False
    response_mode: str = "query"
    extra_authorize: dict[str, str] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return self.configured


# Tests inject a mock transport so no flow ever leaves the process.
transport: httpx.AsyncBaseTransport | None = None
_jwks_cache: dict[str, tuple[float, dict]] = {}
_apple_secret: tuple[float, str] | None = None


def reset_caches() -> None:
    global _apple_secret
    _jwks_cache.clear()
    _apple_secret = None


def apple_client_secret() -> str:
    """Apple wants a short-lived ES256 JWT as the client secret. Cached for a day."""
    global _apple_secret
    now = time.time()
    if _apple_secret and _apple_secret[0] > now:
        return _apple_secret[1]
    claims = {
        "iss": settings.apple_team_id,
        "iat": int(now),
        "exp": int(now) + 86400 * 2,
        "aud": APPLE_ISSUER,
        "sub": settings.apple_client_id,
    }
    pem = settings.apple_private_key.replace("\\n", "\n")
    secret = jwtutil.sign_es256(claims, pem, settings.apple_key_id)
    _apple_secret = (now + 86400, secret)
    return secret


def microsoft_tenant() -> str:
    return settings.microsoft_tenant.strip() or "common"


def registry() -> dict[str, Provider]:
    tenant = microsoft_tenant()
    return {
        "google": Provider(
            "google",
            "Google",
            settings.google_authorize_url,
            settings.google_token_url,
            "openid email profile",
            settings.google_client_id,
            lambda: settings.google_client_secret,
            configured=bool(settings.google_client_id and settings.google_client_secret),
            oidc=True,
            extra_authorize={"prompt": "select_account"},
        ),
        "apple": Provider(
            "apple",
            "Apple",
            settings.apple_authorize_url,
            settings.apple_token_url,
            "name email",
            settings.apple_client_id,
            apple_client_secret,
            configured=bool(
                settings.apple_client_id
                and settings.apple_team_id
                and settings.apple_key_id
                and settings.apple_private_key
            ),
            oidc=True,
            # Apple only returns name and email with form_post, which arrives as a cross-site POST.
            response_mode="form_post",
        ),
        "microsoft": Provider(
            "microsoft",
            "Microsoft",
            settings.microsoft_authorize_url.format(tenant=tenant),
            settings.microsoft_token_url.format(tenant=tenant),
            "openid email profile",
            settings.microsoft_client_id,
            lambda: settings.microsoft_client_secret,
            configured=bool(settings.microsoft_client_id and settings.microsoft_client_secret),
            oidc=True,
            extra_authorize={"prompt": "select_account"},
        ),
        "github": Provider(
            "github",
            "GitHub",
            settings.github_authorize_url,
            settings.github_token_url,
            "read:user user:email",
            settings.github_client_id,
            lambda: settings.github_client_secret,
            configured=bool(settings.github_client_id and settings.github_client_secret),
        ),
    }


def get_provider(provider_id: str) -> Provider:
    provider = registry().get(provider_id)
    if provider is None:
        raise OAuthError("Unknown sign-in provider.")
    if not provider.enabled:
        raise OAuthError(f"Sign in with {provider.name} is not configured on this server.")
    return provider


def redirect_uri(provider_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/auth/oauth/{provider_id}/callback"


def begin(provider_id: str, next_path: str, link_user_id: str | None = None) -> tuple[str, str]:
    """Return (authorization URL, state). The state is also bound to the browser by a cookie."""
    provider = get_provider(provider_id)
    state, verifier = new_token(), new_token() + new_token()[:20]
    nonce = new_token()[:32] if provider.oidc else None
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    store.put_oauth_state(state, provider_id, verifier, next_path, link_user_id, nonce)
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri(provider_id),
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
        "code_challenge": challenge.decode(),
        "code_challenge_method": "S256",
        **provider.extra_authorize,
    }
    if provider.response_mode != "query":
        params["response_mode"] = provider.response_mode
    if nonce:
        params["nonce"] = nonce
    return f"{provider.authorize_url}?{urlencode(params)}", state


async def _jwks(client, url: str, force: bool = False) -> dict:
    cached = _jwks_cache.get(url)
    if cached and cached[0] > time.time() and not force:
        return cached[1]
    keys = (await client.get(url, headers={"Accept": "application/json"})).json()
    if not isinstance(keys, dict) or not isinstance(keys.get("keys"), list):
        raise OAuthError("The provider's signing keys could not be read.")
    _jwks_cache[url] = (time.time() + 3600, keys)
    return keys


async def _verified_claims(client, provider: Provider, id_token: str, nonce: str | None) -> dict:
    url = {
        "google": settings.google_jwks_url,
        "apple": settings.apple_jwks_url,
        "microsoft": settings.microsoft_jwks_url.format(tenant=microsoft_tenant()),
    }[provider.id]
    try:
        try:
            claims = jwtutil.verify_rs256(id_token, await _jwks(client, url))
        except jwtutil.TokenError:
            # Providers rotate keys; refetch once before declaring the token forged.
            claims = jwtutil.verify_rs256(id_token, await _jwks(client, url, force=True))
        issuers = {
            "google": {"https://accounts.google.com", "accounts.google.com"},
            "apple": {APPLE_ISSUER},
            "microsoft": {f"https://login.microsoftonline.com/{claims.get('tid')}/v2.0"},
        }[provider.id]
        jwtutil.check_claims(claims, issuers=issuers, audience=provider.client_id, nonce=nonce)
        if provider.id == "microsoft":
            tenant = microsoft_tenant()
            if (
                tenant not in {"common", "organizations", "consumers"}
                and claims.get("tid") != tenant
            ):
                raise jwtutil.TokenError("That Microsoft account belongs to a different directory.")
            if tenant == "consumers" and claims.get("tid") != MICROSOFT_PERSONAL_TENANT:
                raise jwtutil.TokenError("Only personal Microsoft accounts are accepted here.")
    except jwtutil.TokenError as exc:
        raise OAuthError(
            f"{provider.name} sent an identity we could not trust. Try again."
        ) from exc
    return claims


async def exchange(
    provider_id: str, code: str, verifier: str, nonce: str | None = None, hints: dict | None = None
) -> Profile:
    """Redeem the code and return the person's profile. `hints` carries Apple's first-time name."""
    provider = get_provider(provider_id)
    async with httpx.AsyncClient(transport=transport, timeout=15) as client:
        try:
            token_response = await client.post(
                provider.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(provider_id),
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret(),
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            payload = token_response.json()
            if not isinstance(payload, dict) or token_response.status_code != 200:
                raise OAuthError(f"{provider.name} did not accept the sign-in. Try again.")
            access = payload.get("access_token")
            if provider.oidc:
                id_token = payload.get("id_token")
                if not isinstance(id_token, str):
                    raise OAuthError(f"{provider.name} did not return an identity. Try again.")
                claims = await _verified_claims(client, provider, id_token, nonce)
                return await _oidc_profile(client, provider, claims, access, hints or {})
            if not isinstance(access, str):
                raise OAuthError(f"{provider.name} did not accept the sign-in. Try again.")
            headers = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
            return await _github(client, headers)
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError(f"Could not reach {provider.name}. Try again.") from exc


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _truthy(value) -> bool:
    """Apple sends booleans as the strings "true"/"false"; Google and Microsoft send booleans."""
    return value is True or value == "true"


async def _oidc_profile(client, provider: Provider, claims: dict, access, hints: dict) -> Profile:
    subject = claims["sub"]
    email = _text(claims.get("email")) or None
    if provider.id == "google":
        return Profile(
            subject,
            email,
            _truthy(claims.get("email_verified")),
            _text(claims.get("name")),
            _text(claims.get("picture")) or None,
        )
    if provider.id == "apple":
        # is_private_email addresses are Apple relays: real, verified and deliverable.
        return Profile(
            subject, email, _truthy(claims.get("email_verified")), hints.get("name", ""), None
        )
    # Microsoft. Entra can let a tenant admin put any address on an account they control (nOAuth),
    # so an email is trusted only for personal accounts, or when Microsoft marks the domain as
    # verified with the xms_edov claim. Anything else signs in as "no verified email".
    if not email and isinstance(access, str):
        info = (
            await client.get(
                settings.microsoft_userinfo_url, headers={"Authorization": f"Bearer {access}"}
            )
        ).json()
        email = (_text(info.get("email")) or None) if isinstance(info, dict) else None
    personal = claims.get("tid") == MICROSOFT_PERSONAL_TENANT
    verified = bool(email) and (personal or claims.get("xms_edov") is True)
    return Profile(subject, email, verified, _text(claims.get("name")), None)


async def _github(client, headers) -> Profile:
    data = (await client.get(settings.github_user_url, headers=headers)).json()
    subject = data.get("id")
    if subject is None:
        raise OAuthError("GitHub did not return an account identifier.")
    emails = (await client.get(settings.github_emails_url, headers=headers)).json()
    verified = [e for e in emails if isinstance(e, dict) and e.get("verified") is True]
    primary = next((e for e in verified if e.get("primary")), verified[0] if verified else None)
    name = data.get("name") or data.get("login") or ""
    avatar = data.get("avatar_url") or None
    avatar = avatar if isinstance(avatar, str) else None
    return Profile(
        str(subject),
        primary.get("email") if primary else None,
        primary is not None,
        name if isinstance(name, str) else "",
        avatar,
    )


def apple_name_hint(raw: str | None) -> str:
    """Apple posts the person's name only on first authorisation, as a JSON `user` field."""
    if not raw:
        return ""
    try:
        value = json.loads(raw)
        name = value.get("name", {}) if isinstance(value, dict) else {}
        parts = (_text(name.get("firstName")), _text(name.get("lastName")))
        return " ".join(p for p in parts if p)[:80]
    except (ValueError, AttributeError):
        return ""
