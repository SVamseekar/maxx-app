"""Security activity: an append-only trail per account, with email alerts for key events."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from maxx.auth import mail, store
from maxx.auth.deps import client_ip

# kind -> (label shown in the account, alert headline or None for no email)
KINDS: dict[str, tuple[str, str | None]] = {
    "signup": ("Account created", None),
    "login": ("Signed in with password", None),
    "login_mfa": ("Signed in with password and a verification code", None),
    "login_passkey": ("Signed in with a passkey", None),
    "login_link": ("Signed in with an email link", None),
    "login_oauth": ("Signed in with a provider", None),
    "login_failed": ("Failed sign-in attempt", None),
    "mfa_failed": ("Wrong verification code", None),
    "reauth": ("Confirmed identity for a sensitive change", None),
    "new_device": ("Sign-in from a new device", "There was a sign-in from a new device"),
    "password_changed": ("Password changed", "Your password was changed"),
    "password_reset": ("Password reset by email", "Your password was reset"),
    "mfa_enabled": ("Two-step verification turned on", "Two-step verification was turned on"),
    "mfa_disabled": ("Two-step verification turned off", "Two-step verification was turned off"),
    "recovery_used": ("Recovery code used", "A recovery code was used to sign in"),
    "recovery_regenerated": ("Recovery codes replaced", "Your recovery codes were replaced"),
    "passkey_added": ("Passkey added", "A passkey was added to your account"),
    "passkey_removed": ("Passkey removed", "A passkey was removed from your account"),
    "provider_linked": ("Sign-in provider linked", "A sign-in provider was linked"),
    "provider_unlinked": ("Sign-in provider unlinked", "A sign-in provider was unlinked"),
    "sessions_revoked": ("Signed out of other devices", None),
    "email_verified": ("Email confirmed", None),
}


def ip_prefix(ip: str) -> str:
    """Keep only the network (IPv4 /24, IPv6 /48): enough to spot a new place, not a home."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    length = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{length}", strict=False))


async def record(user: store.User, kind: str, request: Request, detail: str = "") -> None:
    agent = request.headers.get("user-agent", "")
    store.add_event(user.id, kind, ip_prefix(client_ip(request)), agent, detail)
    headline = KINDS.get(kind, ("", None))[1]
    if headline:
        await mail.send_alert(user.email, user.display_name, headline, detail, _where(request))


def _where(request: Request) -> tuple[tuple[str, str], ...]:
    agent = request.headers.get("user-agent", "")
    return (
        ("Device", describe_agent(agent)),
        ("Network", ip_prefix(client_ip(request)) or "unknown"),
    )


def describe_agent(agent: str) -> str:
    """Name the device as the account page does (auth-helpers.ts), such as "Chrome on macOS"."""
    browsers = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Opera", "Opera"), ("Firefox/", "Firefox"))
    browsers += (("Chrome/", "Chrome"), ("Safari/", "Safari"))
    systems = (("iPhone", "iOS"), ("iPad", "iOS"), ("Android", "Android"), ("Mac OS X", "macOS"))
    systems += (("Windows", "Windows"), ("Linux", "Linux"))
    browser = next((name for mark, name in browsers if mark in agent), "")
    system = next((name for mark, name in systems if mark in agent), "")
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown device"


async def note_sign_in(user: store.User, kind: str, request: Request) -> None:
    """Record a sign-in; if this browser and network were never seen for the account, say so."""
    agent = request.headers.get("user-agent", "")
    prefix = ip_prefix(client_ip(request))
    known = store.seen_before(user.id, prefix, agent)
    has_history = bool(store.list_events(user.id, 1))
    store.add_event(user.id, kind, prefix, agent)
    if has_history and not known:
        store.add_event(user.id, "new_device", prefix, agent)
        await mail.send_alert(
            user.email, user.display_name, KINDS["new_device"][1] or "", "", _where(request)
        )
