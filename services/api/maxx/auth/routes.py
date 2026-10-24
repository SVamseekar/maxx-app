"""Account API: sign-up, sign-in (password, email link, OAuth), recovery, sessions, account control.

Two-step verification, passkeys, re-authentication and security activity live in routes_security.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
from typing import Annotated, Literal
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from maxx import hardening, privacy
from maxx.auth import breach, captcha, events, mail, mfa, oauth, ratelimit, store
from maxx.auth.deps import (
    OAUTH_BASE,
    CodedError,
    CurrentUser,
    FreshUser,
    OptionalUser,
    clear_session_cookie,
    client_ip,
    cookie_name,
    is_admin,
    same_origin,
    secure_cookies,
    session_context,
    session_token,
    set_session_cookie,
    set_trusted_cookie,
    trusted_token,
)
from maxx.auth.security import (
    clean_display_name,
    hash_password,
    normalize_email,
    password_problem,
    safe_next,
    valid_email,
    verify_password,
)
from maxx.config import settings
from maxx.negotiate.blocs import leave_member
from maxx.negotiate.contracts import BlocView
from maxx.negotiate.routes import RuntimeDep
from maxx.negotiate.store import Conflict

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(same_origin)])
# No origin check: the provider (not our site) is the legitimate sender. See oauth_form_post.
form_post_router = APIRouter()
me_router = APIRouter(dependencies=[Depends(same_origin)])

VERIFY_TTL, RESET_TTL, SIGNUP_TTL, LINK_TTL, MFA_TTL = 48 * 3600, 3600, 24 * 3600, 900, 300
GENERIC_LOGIN_ERROR = "Incorrect email or password."
METHOD_EVENT = {
    "password": "login",
    "password+totp": "login_mfa",
    "password+recovery": "login_mfa",
    "passkey": "login_passkey",
    "email_link": "login_link",
    "email_link+totp": "login_mfa",
    "email_link+recovery": "login_mfa",
    "oauth": "login_oauth",
    "oauth+totp": "login_mfa",
    "oauth+recovery": "login_mfa",
    "signup": "signup",
}


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Signup(Body):
    email: str = Field(max_length=320)
    display_name: str = Field(default="", max_length=200)
    captcha: str | None = Field(default=None, max_length=2048)


class Login(Body):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    captcha: str | None = Field(default=None, max_length=2048)


class LoginMfa(Body):
    mfa_token: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=4, max_length=32)
    remember: bool = False


class EmailOnly(Body):
    email: str = Field(max_length=320)
    captcha: str | None = Field(default=None, max_length=2048)


class Reset(Body):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)


class Token(Body):
    token: str = Field(min_length=10, max_length=200)


class ChangePassword(Body):
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str = Field(max_length=256)


class Profile(Body):
    display_name: str = Field(min_length=1, max_length=200)


class DeleteAccount(Body):
    confirm: Literal["delete my account"]


def user_payload(user: store.User) -> dict:
    providers = store.list_identities(user.id)
    passkeys = len(store.list_passkeys(user.id))
    return {
        "id": user.id,
        "email": user.email,
        "email_verified": user.email_verified,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "has_password": user.has_password,
        "providers": providers,
        "totp_enabled": user.totp_enabled,
        "passkeys": passkeys,
        # An account nobody can get back into except by emailed link should be told so.
        "needs_credential": not (user.has_password or passkeys or providers),
        "is_admin": is_admin(user),
        "created_at": user.created_at,
    }


# --- shared building blocks ---


async def check_password(password: str, email: str, name: str) -> None:
    """Policy plus breach screening. Raises 422 with a message the person can act on."""
    problem = password_problem(password, email, name)
    if problem:
        raise HTTPException(422, problem)
    if await breach.is_breached(password):
        raise HTTPException(
            422,
            "That password appears in a public data breach, so attackers try it first. "
            "Choose a different one.",
        )


async def require_captcha(request: Request, token: str | None, *, needed: bool = True) -> None:
    if needed and captcha.enabled() and not await captcha.verify(token, client_ip(request)):
        raise CodedError(400, "Complete the verification check to continue.", "captcha_required")


def device_is_trusted(request: Request, user: store.User) -> bool:
    token = trusted_token(request)
    return bool(token) and store.trusted_device_ok(token, user.id)  # type: ignore[arg-type]


async def finish_sign_in(
    user: store.User, method: str, request: Request, response: Response
) -> dict:
    """Create the session. A fresh id every time, so a pre-login cookie can never be reused."""
    previous = session_token(request)
    if previous:
        store.delete_session(previous)
    token = store.create_session(
        user.id, request.headers.get("user-agent", ""), settings.session_days, method
    )
    store.update_user(user.id, last_login_at=store.now())
    set_session_cookie(response, token)
    await events.note_sign_in(user, METHOD_EVENT.get(method, "login"), request)
    if method.endswith("+recovery"):
        await events.record(user, "recovery_used", request)
    return {"user": user_payload(store.get_user(user.id) or user)}


async def primary_sign_in(
    user: store.User, method: str, request: Request, response: Response
) -> dict:
    """One factor succeeded. Finish, or ask for the second when two-step verification is on."""
    if user.totp_enabled and not device_is_trusted(request, user):
        token = store.issue_token(user.id, "mfa_pending:" + method, user.email, MFA_TTL)
        return {"mfa_required": True, "mfa_token": token}
    return await finish_sign_in(user, method, request, response)


# --- discovery ---


@router.get("/providers")
def providers() -> dict:
    return {
        "password": True,
        "oauth": [
            {"id": p.id, "name": p.name, "enabled": p.enabled} for p in oauth.registry().values()
        ],
        "email_mode": "smtp" if settings.email_mode == "smtp" and settings.smtp_host else "log",
        "captcha": {"provider": "turnstile", "site_key": settings.turnstile_site_key}
        if captcha.enabled()
        else None,
    }


@router.get("/me")
def me(user: OptionalUser) -> dict:
    return {"user": user_payload(user) if user else None}


# --- sign-up: confirm the email first, then choose how to sign in ---


@router.post("/signup", status_code=202)
async def signup(body: Signup, request: Request) -> dict:
    """Never reveals whether an address is registered: the reply is the same either way.

    Nothing about the account is chosen here. The emailed link proves the mailbox and signs the
    person in, and only then do they pick a password or passkey. That removes the pre-registration
    takeover (an attacker holding someone else's address with a password they set).
    """
    ip = client_ip(request)
    ratelimit.hit(f"signup:{ip}", 10, 3600)
    await require_captcha(request, body.captcha)
    email = normalize_email(body.email)
    if not valid_email(email):
        raise HTTPException(422, "Enter a valid email address.")
    try:
        ratelimit.hit(f"signup-email:{email}", 3, 3600)
    except HTTPException:
        return {"status": "check_email"}
    user = await asyncio.to_thread(store.get_user_by_email, email)
    if user and (user.email_verified or user.has_password or store.list_identities(user.id)):
        await mail.send_already_registered(email)
    else:
        if user is None:
            name = clean_display_name(body.display_name, email)
            try:
                user = await asyncio.to_thread(store.create_user, email, name, None)
            except store.EmailTaken:  # a concurrent request created it first
                user = store.get_user_by_email(email)
        if user:
            token = store.issue_token(user.id, "signup", email, SIGNUP_TTL)
            await mail.send_signup_link(email, token)
    return {"status": "check_email"}


@router.post("/signup/verify")
async def signup_verify(body: Token, request: Request, response: Response) -> dict:
    ratelimit.hit(f"signup-verify:{client_ip(request)}", 30, 3600)
    claimed = store.consume_token(body.token, "signup")
    user = store.get_user(claimed[0]) if claimed else None
    if claimed is None or user is None or user.email != claimed[1]:
        raise HTTPException(
            400, "This link is invalid or has expired. Start again to get a new one."
        )
    store.update_user(user.id, email_verified=True)
    user = store.get_user(user.id) or user
    await events.record(user, "email_verified", request)
    return await finish_sign_in(user, "signup", request, response)


# --- sign-in ---


@router.post("/login")
async def login(body: Login, request: Request, response: Response) -> dict:
    ip, email = client_ip(request), normalize_email(body.email)
    ratelimit.hit(f"login-ip:{ip}", 60, 900)
    ratelimit.check(f"login-fail:{email}", 8, 900)
    # After a few misses on this address or network, a human check is required (when configured).
    suspicious = ratelimit.count(f"login-fail:{email}", 900) >= 3
    suspicious = suspicious or ratelimit.count(f"login-fail-ip:{ip}", 900) >= 6
    await require_captcha(request, body.captcha, needed=suspicious)
    found = await asyncio.to_thread(store.password_hash_by_email, email)
    stored = found[1] if found else None
    ok = await asyncio.to_thread(verify_password, body.password, stored)
    if not (ok and found):
        ratelimit.record(f"login-fail:{email}")
        ratelimit.record(f"login-fail-ip:{ip}")
        if found:
            owner = store.get_user(found[0])
            if owner:
                store.add_event(
                    owner.id,
                    "login_failed",
                    events.ip_prefix(ip),
                    request.headers.get("user-agent", ""),
                )
        raise HTTPException(401, GENERIC_LOGIN_ERROR)
    user = store.get_user(found[0])
    assert user is not None
    return await primary_sign_in(user, "password", request, response)


@router.post("/login/mfa")
async def login_mfa(body: LoginMfa, request: Request, response: Response) -> dict:
    """Second step. Wrong guesses burn the pending sign-in after five tries."""
    ip = client_ip(request)
    ratelimit.hit(f"mfa-ip:{ip}", 60, 900)
    purpose, claimed = None, None
    for method in ("password", "email_link", "oauth"):
        claimed = store.peek_token(body.mfa_token, "mfa_pending:" + method)
        if claimed:
            purpose = method
            break
    user = store.get_user(claimed[0]) if claimed else None
    if user is None or purpose is None:
        raise HTTPException(401, "This sign-in expired. Start again.")
    ratelimit.check(f"mfa-fail:{user.id}", 8, 900)
    verified = await verify_second_factor(user, body.code)
    if verified is None:
        ratelimit.record(f"mfa-fail:{user.id}")
        failures = ratelimit.count(f"mfa-fail:{user.id}", 900)
        store.add_event(
            user.id, "mfa_failed", events.ip_prefix(ip), request.headers.get("user-agent", "")
        )
        if failures >= 5:
            store.consume_token(body.mfa_token, "mfa_pending:" + purpose)
            raise HTTPException(401, "Too many wrong codes. Start the sign-in again.")
        raise HTTPException(401, "That code is not right. Check your authenticator and try again.")
    if store.consume_token(body.mfa_token, "mfa_pending:" + purpose) is None:
        raise HTTPException(401, "This sign-in expired. Start again.")
    result = await finish_sign_in(user, f"{purpose}+{verified}", request, response)
    if body.remember and verified == "totp":
        set_trusted_cookie(
            response,
            store.add_trusted_device(
                user.id, request.headers.get("user-agent", ""), settings.trusted_device_days
            ),
        )
    return result


async def verify_second_factor(user: store.User, code: str) -> str | None:
    """Return "totp" or "recovery" when the code is valid and unused, else None."""
    from maxx import secrets as vault

    sealed, _pending, enabled = store.totp_material(user.id)
    if not enabled or not sealed:
        return None
    if mfa.looks_like_recovery(code):
        return "recovery" if store.use_recovery_code(user.id, mfa.recovery_hash(code)) else None
    step = mfa.match(vault.decrypt(sealed, "totp"), code)
    if step is not None and store.claim_totp_step(user.id, step):
        return "totp"
    return None


@router.post("/login/link", status_code=202)
async def request_signin_link(body: EmailOnly, request: Request) -> dict:
    """Sign in without a password: a single-use link sent to the mailbox."""
    ratelimit.hit(f"link-ip:{client_ip(request)}", 10, 3600)
    await require_captcha(request, body.captcha)
    email = normalize_email(body.email)
    if valid_email(email):
        try:
            ratelimit.hit(f"link:{email}", 3, 3600)
        except HTTPException:
            return {"status": "sent"}
        user = store.get_user_by_email(email)
        if user and user.email_verified:
            token = store.issue_token(user.id, "signin_link", email, LINK_TTL)
            await mail.send_signin_link(email, user.display_name, token)
    return {"status": "sent"}


@router.post("/login/link/verify")
async def signin_link_verify(body: Token, request: Request, response: Response) -> dict:
    ratelimit.hit(f"link-verify:{client_ip(request)}", 30, 3600)
    claimed = store.consume_token(body.token, "signin_link")
    user = store.get_user(claimed[0]) if claimed else None
    if claimed is None or user is None or user.email != claimed[1]:
        raise HTTPException(400, "This sign-in link is invalid or has expired.")
    return await primary_sign_in(user, "email_link", request, response)


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    token = session_token(request)
    if token:
        store.delete_session(token)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


# --- recovery and verification ---


@router.post("/password/forgot", status_code=202)
async def forgot_password(body: EmailOnly, request: Request) -> dict:
    ratelimit.hit(f"forgot-ip:{client_ip(request)}", 10, 3600)
    await require_captcha(request, body.captcha)
    email = normalize_email(body.email)
    # The reply is identical whether or not the account exists.
    if valid_email(email):
        try:
            ratelimit.hit(f"forgot:{email}", 3, 3600)
        except HTTPException:
            return {"status": "sent"}
        user = store.get_user_by_email(email)
        if user:
            token = store.issue_token(user.id, "reset_password", user.email, RESET_TTL)
            await mail.send_reset(user.email, user.display_name, token)
    return {"status": "sent"}


@router.post("/password/reset")
async def reset_password(body: Reset, request: Request) -> dict:
    ratelimit.hit(f"reset-ip:{client_ip(request)}", 20, 3600)
    expired = "This reset link is invalid or has expired. Request a new one."
    claimed = store.peek_token(body.token, "reset_password")
    user = store.get_user(claimed[0]) if claimed else None
    if user is None:
        raise HTTPException(400, expired)
    await check_password(body.password, user.email, user.display_name)
    password_hash = await asyncio.to_thread(hash_password, body.password)
    if store.consume_token(body.token, "reset_password") is None:  # lost a race with another use
        raise HTTPException(400, expired)
    # Following a mailed link proves control of the mailbox. Everything signed in before this is
    # ended, including remembered browsers; two-step verification stays on.
    store.update_user(user.id, password_hash=password_hash, email_verified=True)
    store.revoke_other_sessions(user.id, None)
    store.revoke_trusted_devices(user.id)
    await events.record(user, "password_reset", request)
    return {"status": "reset"}


@router.post("/email/verify")
def verify_email(body: Token, request: Request) -> dict:
    ratelimit.hit(f"verify-ip:{client_ip(request)}", 30, 3600)
    claimed = store.consume_token(body.token, "verify_email")
    user = store.get_user(claimed[0]) if claimed else None
    if claimed is None or user is None or user.email != claimed[1]:
        raise HTTPException(400, "This confirmation link is invalid or has expired.")
    store.update_user(user.id, email_verified=True)
    return {"status": "verified"}


@router.post("/email/resend", status_code=202)
async def resend_verification(user: CurrentUser) -> dict:
    if user.email_verified:
        return {"status": "already_verified"}
    ratelimit.hit(f"resend:{user.id}", 3, 3600)
    token = store.issue_token(user.id, "verify_email", user.email, VERIFY_TTL)
    await mail.send_verification(user.email, user.display_name, token)
    return {"status": "sent"}


# --- profile, password, sessions ---


@router.patch("/me")
def update_profile(body: Profile, user: CurrentUser) -> dict:
    name = " ".join(body.display_name.split())[:80]
    if not name:
        raise HTTPException(422, "Enter a name.")
    store.update_user(user.id, display_name=name)
    return {"user": user_payload(store.get_user(user.id))}  # type: ignore[arg-type]


@router.post("/password/change")
async def change_password(
    body: ChangePassword, request: Request, response: Response, user: FreshUser
) -> dict:
    ratelimit.hit(f"pwchange:{user.id}", 10, 900)
    stored = store.password_hash_for(user.id)
    if stored:
        if not body.current_password or not await asyncio.to_thread(
            verify_password, body.current_password, stored
        ):
            raise HTTPException(403, "Your current password is incorrect.")
    await check_password(body.new_password, user.email, user.display_name)
    password_hash = await asyncio.to_thread(hash_password, body.new_password)
    store.update_user(user.id, password_hash=password_hash)
    token = session_token(request)
    revoked = store.revoke_other_sessions(user.id, token)
    store.revoke_trusted_devices(user.id)
    if token:  # a privilege change gets a new session id
        set_session_cookie(
            response,
            store.rotate_session(
                token, request.headers.get("user-agent", ""), settings.session_days, "password"
            ),
        )
    await events.record(user, "password_changed", request)
    return {"status": "changed", "signed_out_elsewhere": revoked}


@router.get("/sessions")
def sessions(request: Request, user: CurrentUser) -> dict:
    token = session_token(request)
    current = store.current_public_id(token) if token else ""
    return {
        "sessions": [
            {
                "id": s.public_id,
                "current": s.public_id == current,
                "created_at": s.created_at,
                "last_seen_at": s.last_seen_at,
                "user_agent": s.user_agent,
            }
            for s in store.list_sessions(user.id)
        ],
        "trusted_devices": store.count_trusted_devices(user.id),
    }


@router.post("/sessions/revoke-others")
async def revoke_others(request: Request, user: FreshUser) -> dict:
    revoked = store.revoke_other_sessions(user.id, session_token(request))
    store.revoke_trusted_devices(user.id)
    await events.record(user, "sessions_revoked", request, f"{revoked} device(s)")
    return {"revoked": revoked}


@router.delete("/sessions/{public_id}", status_code=204)
def revoke_one(public_id: str, request: Request, user: FreshUser) -> Response:
    if not public_id.isalnum() or len(public_id) != 16:
        raise HTTPException(404, "Session not found.")
    token = session_token(request)
    if token and public_id == store.current_public_id(token):
        raise HTTPException(409, "Use sign out to end this session.")
    if not store.revoke_session(user.id, public_id):
        raise HTTPException(404, "Session not found.")
    return Response(status_code=204)


@router.delete("/oauth/{provider}", status_code=204)
async def unlink_provider(provider: str, request: Request, user: FreshUser) -> Response:
    linked = store.list_identities(user.id)
    if provider not in linked:
        raise HTTPException(404, "That sign-in method is not linked.")
    if not (user.has_password or store.list_passkeys(user.id)) and len(linked) <= 1:
        raise HTTPException(
            409, "Add a password or passkey first. Otherwise you would lose access to this account."
        )
    store.unlink_identity(user.id, provider)
    await events.record(user, "provider_unlinked", request, provider)
    return Response(status_code=204)


async def release_holds(runtime, user_id: str) -> None:
    """Void every PayPal hold this account has on Blocs that have not finished."""
    from maxx.money import ledger, service

    if not service.enabled():
        return
    for payment in ledger.for_user(user_id):
        if payment["kind"] == "hold" and payment["status"] in {"AUTHORIZED", "CREATED", "APPROVED"}:
            bloc = runtime.store.get(payment["bloc_id"]) if payment["bloc_id"] else None
            if bloc is not None and bloc.status == "OPEN":
                try:
                    await service.leave(runtime.store, bloc, user_id)
                except ValueError:
                    pass
            elif payment["status"] in {"CREATED", "APPROVED"}:
                ledger.update_payment(payment["id"], status="FAILED", error="account_closed")


def scrub_account_from_blocs(runtime, user_id: str) -> None:
    """Release open commitments and strip the account id from every Bloc it touched."""
    for bloc in runtime.store.list_for_user(user_id):
        for _ in range(3):  # a concurrent save is retried against the fresh revision
            try:
                if bloc.status == "OPEN":
                    leave_member(bloc, user_id)
                for member in bloc.members:
                    if member.user_id == user_id:
                        member.user_id = "deleted-account"
                if bloc.owner_id == user_id:
                    bloc.owner_id = None
                runtime.store.save(bloc)
                break
            except Conflict:
                bloc = runtime.store.get(bloc.id)


@router.post("/me/delete", status_code=204)
async def delete_account(body: DeleteAccount, user: FreshUser, runtime: RuntimeDep) -> Response:
    ratelimit.hit(f"delete:{user.id}", 5, 900)
    if any(
        b.status == "NEGOTIATING" and any(m.user_id == user.id for m in b.members)
        for b in runtime.store.list()
    ):
        raise HTTPException(409, "A negotiation you joined is running. Try again when it finishes.")
    reasons = privacy.blockers(user.id)
    if reasons:
        raise HTTPException(409, " ".join(reasons) + " Finish these, then close your account.")
    await release_holds(runtime, user.id)
    scrub_account_from_blocs(runtime, user.id)
    privacy.erase(user.id)
    store.delete_user(user.id)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


# --- OAuth ---


def _redirect(location: str) -> RedirectResponse:
    response = RedirectResponse(location, status_code=302)
    response.delete_cookie(cookie_name(OAUTH_BASE), path="/")
    return response


def _bounce(error: str, path: str = "/login") -> RedirectResponse:
    return _redirect(f"{path}?error={error}")


@router.get("/oauth/{provider}/start")
async def oauth_start(
    provider: str,
    request: Request,
    next: Annotated[str | None, Query(max_length=300)] = None,
    link: bool = False,
) -> RedirectResponse:
    context = await session_context(request)
    user = context[0] if context else None
    if link:
        if context is None:
            return _bounce("signin_required")
        if store.now() - context[1].recent_auth_at > settings.reauth_minutes * 60:
            return _bounce("reauth_required", "/account")
    try:
        url, state = oauth.begin(provider, safe_next(next), user.id if link and user else None)
    except oauth.OAuthError:
        return _bounce("oauth_unavailable")
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        cookie_name(OAUTH_BASE),
        state,
        max_age=600,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )
    return response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    user: OptionalUser,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=200)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
    user_hint: Annotated[str | None, Query(alias="user", max_length=2000)] = None,
) -> RedirectResponse:
    ratelimit.hit(f"oauth-cb:{client_ip(request)}", 30, 900)
    if error or not code or not state:
        return _bounce("oauth_denied")
    cookie = request.cookies.get(cookie_name(OAUTH_BASE), "")
    # The cookie binds this callback to the browser that started the flow (login-CSRF defence).
    if not cookie or not hmac.compare_digest(cookie, state):
        return _bounce("oauth_state")
    row = store.pop_oauth_state(state, provider)
    if row is None:
        return _bounce("oauth_state")
    try:
        hints = {"name": oauth.apple_name_hint(user_hint)} if provider == "apple" else {}
        profile = await oauth.exchange(provider, code, row.verifier, row.nonce, hints)
    except oauth.OAuthError:
        return _bounce("oauth_failed")

    response = _redirect(safe_next(row.next_path))
    email = normalize_email(profile.email) if profile.email else None

    owner_id = store.identity_owner(provider, profile.subject)
    if row.link_user_id:  # linking from account settings
        if user is None or user.id != row.link_user_id:
            return _bounce("signin_required")
        if owner_id and owner_id != user.id:
            return _bounce("oauth_taken", "/account")
        if not owner_id:
            try:
                store.link_identity(provider, profile.subject, user.id, email)
            except store.EmailTaken:
                return _bounce("oauth_taken", "/account")
            await events.record(user, "provider_linked", request, provider)
        return _redirect("/account?linked=" + provider)

    if owner_id:
        account = store.get_user(owner_id)
    elif not email or not profile.email_verified or not valid_email(email):
        return _bounce("oauth_no_email")
    else:
        account = store.get_user_by_email(email)
        if account and (account.totp_enabled or store.list_passkeys(account.id)):
            # A provider matching this address must not be able to sidestep two-step verification
            # or a passkey. Sign in with your own method first, then link it from your account.
            return _bounce("oauth_link_required")
        try:
            if account is None:
                account = store.create_user(
                    email, clean_display_name(profile.name, email), None, True, profile.avatar_url
                )
            elif not account.email_verified:
                # Pre-hijacking defence: whoever registered this address never proved they own it.
                # The provider just did, so drop any unproven password and every existing session
                # before attaching the identity; only the real owner keeps access.
                store.update_user(account.id, email_verified=True, password_hash=None)
                store.revoke_other_sessions(account.id, None)
            # The provider verified this address, so attaching it cannot hand over the account.
            store.link_identity(provider, profile.subject, account.id, email)
        except store.EmailTaken:
            return _bounce("oauth_failed")
    if account is None:
        return _bounce("oauth_failed")
    # The provider vouched for who this is, but an account that turned on two-step verification
    # still asks for its own second factor unless this browser was trusted.
    if account.totp_enabled and not device_is_trusted(request, account):
        token = store.issue_token(account.id, "mfa_pending:oauth", account.email, MFA_TTL)
        return _redirect(f"/login?mfa={token}&next={quote(safe_next(row.next_path), safe='')}")
    await finish_sign_in(account, "oauth", request, response)
    return response


@form_post_router.post("/oauth/{provider}/callback")
async def oauth_form_post(provider: str, request: Request) -> HTMLResponse:
    """Providers using response_mode=form_post (Apple) POST the result from their own site.

    That cross-site POST carries no SameSite=Lax cookie, so it only forwards the parameters to the
    matching GET callback from a page on this origin. There the state cookie is present and every
    check runs. Nothing is trusted or acted on here.
    """
    if provider not in oauth.registry():
        raise HTTPException(404, "Unknown sign-in provider.")
    ratelimit.hit(f"oauth-post:{client_ip(request)}", 30, 900)
    body = (await request.body())[:8192].decode("utf-8", "replace")
    form = {k: v[0] for k, v in parse_qs(body, keep_blank_values=False).items()}
    allowed = {k: v[:2048] for k, v in form.items() if k in {"code", "state", "error", "user"}}
    target = f"/api/auth/oauth/{provider}/callback?{urlencode(allowed)}"
    nonce = hardening.csp_nonce()
    page = (
        '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
        "<title>Signing you in…</title>"
        f'<script nonce="{nonce}">location.replace({json.dumps(target)})</script>'
        f'<noscript><a href="{html.escape(target)}">Continue to Maxx</a></noscript>'
    )
    return HTMLResponse(
        page,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                f"default-src 'none'; script-src 'nonce-{nonce}'; frame-ancestors 'none'; "
                "base-uri 'none'"
            ),
        },
    )


@me_router.get("/me/export")
def export_my_data(user: FreshUser) -> Response:
    """Everything held about this account, as a download (GDPR access and portability)."""
    ratelimit.hit(f"export:{user.id}", 5, 3600)
    body = json.dumps(privacy.export(user.id), indent=2, default=str)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="maxx-my-data.json"'},
    )


# --- the signed-in person's Blocs ---


@me_router.get("/me/blocs", response_model=list[BlocView])
def my_blocs(runtime: RuntimeDep, user: CurrentUser):
    return [b.public(user.id) for b in runtime.store.list_for_user(user.id)]
