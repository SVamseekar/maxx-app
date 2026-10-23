"""Stronger sign-in: re-authentication, two-step verification, passkeys and security activity."""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from maxx import secrets as vault
from maxx.auth import events, mail, mfa, ratelimit, store
from maxx.auth.deps import (
    CurrentUser,
    FreshUser,
    client_ip,
    same_origin,
    session_token,
    set_session_cookie,
)
from maxx.auth.routes import finish_sign_in, verify_second_factor
from maxx.auth.security import verify_password
from maxx.config import settings

router = APIRouter(dependencies=[Depends(same_origin)])
CODE_TTL = 600
CHALLENGE_TTL = 300


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reauth(Body):
    method: Literal["password", "totp", "email_code", "passkey"]
    password: str | None = Field(default=None, max_length=256)
    code: str | None = Field(default=None, max_length=32)
    challenge_id: str | None = Field(default=None, max_length=80)
    credential: dict[str, Any] | None = None


class Code(Body):
    code: str = Field(min_length=4, max_length=32)


class PasskeyRegistration(Body):
    challenge_id: str = Field(max_length=80)
    credential: dict[str, Any]
    name: str = Field(default="", max_length=80)


class PasskeyLogin(Body):
    challenge_id: str = Field(max_length=80)
    credential: dict[str, Any]


class Rename(Body):
    name: str = Field(min_length=1, max_length=80)


# --- WebAuthn plumbing ---


def relying_party() -> tuple[str, str]:
    """(rp_id, origin). Passkeys are bound to this exact host, so a look-alike site gets nothing."""
    parts = urlsplit(settings.public_base_url)
    return settings.webauthn_rp_id or (
        parts.hostname or "localhost"
    ), f"{parts.scheme}://{parts.netloc}"


def _descriptors(user_id: str) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.id))
        for p in store.list_passkeys(user_id)
    ]


def _options_payload(options, challenge_id: str) -> dict:
    return {"options": json.loads(options_to_json(options)), "challenge_id": challenge_id}


# --- re-authentication ---


@router.get("/reauth/methods")
def reauth_methods(user: CurrentUser) -> dict:
    return {
        "password": user.has_password,
        "totp": user.totp_enabled,
        "passkey": bool(store.list_passkeys(user.id)),
        "email_code": True,
    }


@router.post("/reauth/email/send", status_code=202)
async def reauth_email_send(user: CurrentUser) -> dict:
    """A six-digit code by email, for people whose account has no password or passkey."""
    ratelimit.hit(f"reauth-code:{user.id}", 5, 3600)
    code = f"{secrets.randbelow(10**6):06d}"
    store.issue_custom_token(user.id, "reauth_code", user.email, f"{user.id}:{code}", CODE_TTL)
    await mail.send_code(user.email, user.display_name, code)
    return {"status": "sent"}


@router.post("/reauth/passkey/options")
def reauth_passkey_options(user: CurrentUser) -> dict:
    ratelimit.hit(f"reauth-pk:{user.id}", 20, 900)
    if not store.list_passkeys(user.id):
        raise HTTPException(409, "No passkey is set up on this account.")
    rp_id, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=_descriptors(user.id),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = store.put_challenge(
        "reauth", user.id, bytes_to_base64url(options.challenge), CHALLENGE_TTL
    )
    return _options_payload(options, challenge_id)


@router.post("/reauth/check")
def reauth_check(user: FreshUser) -> dict:
    """Succeeds only while the identity check is fresh; lets the interface ask early."""
    return {"status": "fresh"}


@router.post("/reauth")
async def reauth(body: Reauth, request: Request, user: CurrentUser) -> dict:
    """Prove it is still you before a sensitive change. Valid for REAUTH_MINUTES."""
    ratelimit.hit(f"reauth-ip:{client_ip(request)}", 60, 900)
    ratelimit.check(f"reauth-fail:{user.id}", 8, 900)
    ok = False
    if body.method == "password":
        stored = store.password_hash_for(user.id)
        ok = bool(stored and body.password) and await asyncio.to_thread(
            verify_password, body.password or "", stored
        )
    elif body.method == "totp":
        ok = bool(body.code) and await verify_second_factor(user, body.code or "") is not None
    elif body.method == "email_code":
        ok = (
            bool(body.code)
            and store.consume_token(f"{user.id}:{body.code}", "reauth_code") is not None
        )
    elif body.method == "passkey" and body.challenge_id and body.credential:
        ok = (
            _verify_assertion(body.challenge_id, "reauth", body.credential, expected_user=user.id)
            is not None
        )
    if not ok:
        ratelimit.record(f"reauth-fail:{user.id}")
        raise HTTPException(403, "That did not match. Check it and try again.")
    token = session_token(request)
    if token:
        store.touch_recent_auth(token)
    return {"status": "fresh", "valid_minutes": settings.reauth_minutes}


# --- two-step verification (authenticator app) ---


@router.post("/mfa/totp/setup")
def totp_setup(user: FreshUser) -> dict:
    """Start enrolment: a new seed that does nothing until a code from it is confirmed."""
    ratelimit.hit(f"totp-setup:{user.id}", 10, 3600)
    if user.totp_enabled:
        raise HTTPException(409, "Two-step verification is already on.")
    seed = mfa.new_seed()
    store.set_totp_pending(user.id, vault.encrypt(seed, "totp"))
    return {"secret": seed, "otpauth_uri": mfa.otpauth_uri(seed, user.email)}


@router.post("/mfa/totp/enable")
async def totp_enable(body: Code, request: Request, response: Response, user: FreshUser) -> dict:
    ratelimit.hit(f"totp-enable:{user.id}", 10, 900)
    _active, pending, _enabled = store.totp_material(user.id)
    if not pending:
        raise HTTPException(409, "Start setup first.")
    step = mfa.match(vault.decrypt(pending, "totp"), body.code)
    if step is None or not store.enable_totp(user.id, step):
        raise HTTPException(422, "That code is not right. Check your authenticator and try again.")
    codes = mfa.new_recovery_codes()
    store.replace_recovery_codes(user.id, [mfa.recovery_hash(c) for c in codes])
    token = session_token(request)
    store.revoke_other_sessions(user.id, token)  # a new factor invalidates every other sign-in
    store.revoke_trusted_devices(user.id)
    if token:
        set_session_cookie(
            response,
            store.rotate_session(
                token, request.headers.get("user-agent", ""), settings.session_days, "password"
            ),
        )
    await events.record(user, "mfa_enabled", request)
    return {"recovery_codes": codes}


@router.post("/mfa/totp/disable")
async def totp_disable(body: Code, request: Request, user: FreshUser) -> dict:
    ratelimit.hit(f"totp-disable:{user.id}", 10, 900)
    if await verify_second_factor(user, body.code) is None:
        raise HTTPException(403, "That code is not right.")
    store.disable_totp(user.id)
    await events.record(user, "mfa_disabled", request)
    return {"status": "disabled"}


@router.post("/mfa/recovery/regenerate")
async def recovery_regenerate(body: Code, request: Request, user: FreshUser) -> dict:
    ratelimit.hit(f"recovery-regen:{user.id}", 10, 900)
    if not user.totp_enabled:
        raise HTTPException(409, "Turn on two-step verification first.")
    sealed, _pending, _enabled = store.totp_material(user.id)
    step = mfa.match(vault.decrypt(sealed or "", "totp"), body.code) if sealed else None
    if step is None or not store.claim_totp_step(user.id, step):
        raise HTTPException(403, "Enter a current code from your authenticator app.")
    codes = mfa.new_recovery_codes()
    store.replace_recovery_codes(user.id, [mfa.recovery_hash(c) for c in codes])
    await events.record(user, "recovery_regenerated", request)
    return {"recovery_codes": codes}


# --- passkeys ---


@router.post("/passkeys/register/options")
def passkey_register_options(user: FreshUser) -> dict:
    ratelimit.hit(f"pk-reg:{user.id}", 20, 3600)
    rp_id, _ = relying_party()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=_descriptors(user.id),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    challenge_id = store.put_challenge(
        "register", user.id, bytes_to_base64url(options.challenge), CHALLENGE_TTL
    )
    return _options_payload(options, challenge_id)


@router.post("/passkeys/register/verify")
async def passkey_register_verify(
    body: PasskeyRegistration, request: Request, user: FreshUser
) -> dict:
    ratelimit.hit(f"pk-reg-verify:{user.id}", 20, 3600)
    row = store.pop_challenge(body.challenge_id, "register")
    if row is None or row.user_id != user.id:
        raise HTTPException(400, "That passkey request expired. Try again.")
    rp_id, origin = relying_party()
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError):
        raise HTTPException(400, "That passkey could not be verified. Try again.") from None
    transports = ",".join(
        t
        for t in (body.credential.get("response", {}).get("transports") or [])
        if isinstance(t, str)
    )
    name = " ".join(body.name.split()) or "Passkey"
    try:
        store.add_passkey(
            bytes_to_base64url(verified.credential_id),
            user.id,
            bytes_to_base64url(verified.credential_public_key),
            verified.sign_count,
            name,
            transports,
            str(verified.aaguid),
            verified.credential_device_type.value == "multi_device",
            bool(verified.credential_backed_up),
        )
    except store.EmailTaken:
        raise HTTPException(409, "That passkey is already registered.") from None
    await events.record(user, "passkey_added", request, name)
    return {"status": "added", "name": name}


@router.post("/passkeys/login/options")
def passkey_login_options(request: Request) -> dict:
    """Usernameless: the browser offers whichever passkeys it holds for this site."""
    ratelimit.hit(f"pk-login-options:{client_ip(request)}", 60, 900)
    rp_id, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    challenge_id = store.put_challenge(
        "login", None, bytes_to_base64url(options.challenge), CHALLENGE_TTL
    )
    return _options_payload(options, challenge_id)


def _verify_assertion(
    challenge_id: str, purpose: str, credential: dict, expected_user: str | None
) -> store.Passkey | None:
    """Check a passkey assertion against its one-use challenge. Returns the credential or None."""
    row = store.pop_challenge(challenge_id, purpose)
    credential_id = credential.get("id") if isinstance(credential, dict) else None
    if row is None or not isinstance(credential_id, str):
        return None
    passkey = store.get_passkey(credential_id)
    if passkey is None or (expected_user and passkey.user_id != expected_user):
        return None
    if purpose == "reauth" and row.user_id != passkey.user_id:
        return None
    rp_id, origin = relying_party()
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError):
        return None
    store.passkey_used(passkey.id, verified.new_sign_count, bool(verified.credential_backed_up))
    return passkey


@router.post("/passkeys/login/verify")
async def passkey_login_verify(body: PasskeyLogin, request: Request, response: Response) -> dict:
    ratelimit.hit(f"pk-login-verify:{client_ip(request)}", 60, 900)
    passkey = _verify_assertion(body.challenge_id, "login", body.credential, expected_user=None)
    user = store.get_user(passkey.user_id) if passkey else None
    if user is None:
        raise HTTPException(401, "That passkey was not accepted.")
    # A passkey proves possession and user verification, so it satisfies two-step on its own.
    return await finish_sign_in(user, "passkey", request, response)


@router.patch("/passkeys/{credential_id}")
def passkey_rename(credential_id: str, body: Rename, user: CurrentUser) -> dict:
    name = " ".join(body.name.split())
    if not name or not store.rename_passkey(user.id, credential_id, name):
        raise HTTPException(404, "Passkey not found.")
    return {"status": "renamed"}


@router.delete("/passkeys/{credential_id}", status_code=204)
async def passkey_delete(credential_id: str, request: Request, user: FreshUser) -> Response:
    keys = store.list_passkeys(user.id)
    if credential_id not in {k.id for k in keys}:
        raise HTTPException(404, "Passkey not found.")
    others = len(keys) - 1
    if not (user.has_password or store.list_identities(user.id) or others):
        raise HTTPException(
            409, "Add a password or another sign-in method first, or you would be locked out."
        )
    store.delete_passkey(user.id, credential_id)
    await events.record(user, "passkey_removed", request)
    return Response(status_code=204)


# --- overview and activity ---


def _checkup(user: store.User, passkeys: int, providers: list[str]) -> dict:
    items = [
        {"id": "email", "label": "Email confirmed", "done": user.email_verified, "weight": 20},
        {
            "id": "signin",
            "label": "A way to sign back in",
            "done": bool(user.has_password or passkeys or providers),
            "weight": 20,
        },
        {"id": "passkey", "label": "Passkey (phishing-proof)", "done": passkeys > 0, "weight": 30},
        {
            "id": "mfa",
            "label": "Two-step verification",
            "done": user.totp_enabled or passkeys > 0,
            "weight": 30,
        },
    ]
    return {"score": sum(i["weight"] for i in items if i["done"]), "items": items}


@router.get("/security")
def security_overview(user: CurrentUser) -> dict:
    keys = store.list_passkeys(user.id)
    providers = store.list_identities(user.id)
    return {
        "totp_enabled": user.totp_enabled,
        "recovery_codes_left": store.recovery_codes_left(user.id) if user.totp_enabled else 0,
        "trusted_devices": store.count_trusted_devices(user.id),
        "passkeys": [
            {
                "id": k.id,
                "name": k.name,
                "created_at": k.created_at,
                "last_used_at": k.last_used_at,
                "synced": k.backup_state,
            }
            for k in keys
        ],
        "checkup": _checkup(user, len(keys), providers),
    }


@router.delete("/trusted-devices", status_code=204)
def trusted_devices_revoke(user: FreshUser) -> Response:
    store.revoke_trusted_devices(user.id)
    return Response(status_code=204)


@router.get("/activity")
def activity(user: CurrentUser) -> dict:
    return {
        "events": [
            {
                "id": e.id,
                "kind": e.kind,
                "label": events.KINDS.get(e.kind, (e.kind, None))[0],
                "created_at": e.created_at,
                "network": e.ip_prefix,
                "user_agent": e.user_agent,
                "detail": e.detail,
                "alert": e.kind in {"login_failed", "mfa_failed", "new_device", "recovery_used"},
            }
            for e in store.list_events(user.id, 50)
        ]
    }
