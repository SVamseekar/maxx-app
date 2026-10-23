"""Request-level auth: cookie sessions, same-origin enforcement and client identity."""

from __future__ import annotations

import asyncio
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response

from maxx.auth import store
from maxx.config import settings


def secure_cookies() -> bool:
    return settings.public_base_url.startswith("https://")


def cookie_name(base: str) -> str:
    """`__Host-` pins a cookie to this exact host over https: no Domain, Path=/, Secure required."""
    return f"__Host-{base}" if secure_cookies() else base


SESSION_BASE, OAUTH_BASE, TRUSTED_BASE = "maxx_session", "maxx_oauth_state", "maxx_trusted"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


def allowed_origins() -> set[str]:
    values = [settings.public_base_url, *settings.extra_allowed_origins.split(",")]
    return {o for o in (_origin(v) for v in values if v.strip()) if o}


async def same_origin(request: Request) -> None:
    """Block cross-site writes. Browsers always send Origin on cross-origin POSTs."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        origin = _origin(referer) if referer else None
    if origin is not None and origin.lower() not in allowed_origins():
        raise HTTPException(403, "This request came from an unrecognised site and was blocked.")


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"


def session_token(request: Request) -> str | None:
    return request.cookies.get(cookie_name(SESSION_BASE))


class CodedError(HTTPException):
    """An error the interface can act on: `code` tells it which prompt to show."""

    def __init__(self, status: int, detail: str, code: str):
        super().__init__(status, detail)
        self.code = code


async def session_context(request: Request) -> tuple[store.User, store.SessionRow] | None:
    """Resolve the session once per request."""
    if hasattr(request.state, "maxx_session"):
        return request.state.maxx_session
    token = session_token(request)
    context = None
    if token:
        context = await asyncio.to_thread(store.session_user, token, settings.session_idle_days)
    request.state.maxx_session = context
    return context


SessionContext = Annotated["tuple[store.User, store.SessionRow] | None", Depends(session_context)]


async def optional_user(
    context: Annotated[tuple[store.User, store.SessionRow] | None, Depends(session_context)],
) -> store.User | None:
    return context[0] if context else None


async def require_user(user: Annotated[store.User | None, Depends(optional_user)]) -> store.User:
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


async def fresh_user(
    context: Annotated[tuple[store.User, store.SessionRow] | None, Depends(session_context)],
) -> store.User:
    """Sensitive changes need a recent password, passkey or code check, even when signed in."""
    if context is None:
        raise HTTPException(401, "Sign in to continue.")
    user, session = context
    if store.now() - session.recent_auth_at > settings.reauth_minutes * 60:
        raise CodedError(403, "Confirm it's you to continue.", "reauth_required")
    return user


async def ensure_fresh(request: Request) -> store.User:
    """Like `fresh_user`, for routes that only need it above some amount."""
    return await fresh_user(await session_context(request))


OptionalUser = Annotated[store.User | None, Depends(optional_user)]
CurrentUser = Annotated[store.User, Depends(require_user)]
FreshUser = Annotated[store.User, Depends(fresh_user)]


def trusted_token(request: Request) -> str | None:
    return request.cookies.get(cookie_name(TRUSTED_BASE))


def set_trusted_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        cookie_name(TRUSTED_BASE),
        token,
        max_age=settings.trusted_device_days * 86400,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )


def clear_trusted_cookie(response: Response) -> None:
    response.delete_cookie(
        cookie_name(TRUSTED_BASE), path="/", secure=secure_cookies(), samesite="lax", httponly=True
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        cookie_name(SESSION_BASE),
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        cookie_name(SESSION_BASE), path="/", secure=secure_cookies(), samesite="lax", httponly=True
    )


def is_admin(user: store.User) -> bool:
    admins = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    return user.email_verified and user.email in admins
