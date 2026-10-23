"""Accounts: verify-first sign-up, sign-in, recovery, sessions, freshness, ownership and privacy."""

import hashlib
import re

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from maxx.auth import breach, captcha, mail, store
from maxx.auth.security import (
    hash_password,
    password_problem,
    safe_next,
    valid_email,
    verify_password,
)
from maxx.config import settings
from maxx.main import app
from maxx.negotiate.routes import Runtime, get_runtime
from maxx.negotiate.store import BlocStore
from tests.conftest import sign_up

PASSWORD = "correct horse battery"
OTHER = "another good passphrase"


@pytest.fixture
def runtime(tmp_path):
    value = Runtime(BlocStore(f"sqlite:///{tmp_path}/api.sqlite"), mode="fixture", delay=0)
    value.seed()
    app.dependency_overrides[get_runtime] = lambda: value
    yield value
    app.dependency_overrides.clear()


def token_from_mail(index=-1, path=None) -> str:
    messages = [m for m in mail.outbox if path is None or path in m["text"]]
    match = re.search(r"token=([\w-]+)", messages[index]["text"])
    assert match, messages[index]
    return match.group(1)


def request_signup(client, email="new@example.com", **extra):
    return client.post("/auth/signup", json={"email": email, **extra})


def login(client, email, password=PASSWORD, **headers):
    return client.post("/auth/login", json={"email": email, "password": password}, headers=headers)


# --- primitives ---


def test_password_hash_roundtrip_and_salting():
    first, second = hash_password("a long enough secret"), hash_password("a long enough secret")
    assert first != second and first.startswith("scrypt$")
    assert verify_password("a long enough secret", first)
    assert not verify_password("a long enough secreT", first)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "plaintext-not-a-hash")


def test_password_policy_email_and_redirect_safety():
    assert password_problem("short") is not None
    assert password_problem("password123") is not None
    assert password_problem("aaaaaaaaaaaa") is not None
    assert password_problem("buyername", "buyername@example.com") is not None
    assert password_problem("a perfectly fine passphrase") is None
    assert valid_email("a.b+c@example.co.uk")
    assert not valid_email("a@b") and not valid_email("x y@z.io")
    assert safe_next("/blocs?x=1") == "/blocs?x=1"
    for bad in ["//evil.com", "https://evil.com", "/\\evil.com", "javascript:alert(1)", "", None]:
        assert safe_next(bad) == "/"


# --- verify-first sign-up ---


def test_signup_sends_a_link_and_creates_no_session_or_password():
    with TestClient(app) as client:
        response = request_signup(client, " New@Example.COM ", display_name="  Nova  Q ")
        assert response.status_code == 202 and response.json() == {"status": "check_email"}
        assert "set-cookie" not in response.headers
        assert client.get("/auth/me").json() == {"user": None}
        last = mail.outbox[-1]
        assert last["to"] == "new@example.com" and "complete-signup" in last["text"]
        user = store.get_user_by_email("new@example.com")
        assert user and not user.email_verified and not user.has_password
        assert user.display_name == "Nova Q"
        assert login(client, "new@example.com").status_code == 401  # nothing signs in unproven


def test_signup_reveals_nothing_about_existing_accounts():
    with TestClient(app) as client, TestClient(app) as other:
        sign_up(client, "taken@example.com")
        mail.outbox.clear()
        fresh = request_signup(other, "brand-new@example.com")
        again = request_signup(other, "taken@example.com")
        assert fresh.status_code == again.status_code == 202 and fresh.json() == again.json()
        assert [m["to"] for m in mail.outbox] == ["brand-new@example.com", "taken@example.com"]
        assert "complete-signup" not in mail.outbox[1]["text"]
        assert "already" in mail.outbox[1]["subject"].lower()
        assert store.get_user_by_email("taken@example.com").has_password


def test_following_the_link_signs_in_and_it_works_once():
    with TestClient(app) as client:
        request_signup(client, "v@example.com")
        token = token_from_mail()
        assert client.post("/auth/signup/verify", json={"token": "x" * 30}).status_code == 400
        done = client.post("/auth/signup/verify", json={"token": token})
        assert done.status_code == 200
        user = done.json()["user"]
        assert user["email_verified"] is True and user["needs_credential"] is True
        cookie = done.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
        assert client.get("/auth/me").json()["user"]["id"] == user["id"]
        assert client.post("/auth/signup/verify", json={"token": token}).status_code == 400


def test_a_second_signup_request_replaces_the_first_link():
    with TestClient(app) as client:
        request_signup(client, "r@example.com")
        old = token_from_mail()
        request_signup(client, "r@example.com")
        new = token_from_mail()
        assert old != new
        assert client.post("/auth/signup/verify", json={"token": old}).status_code == 400
        assert client.post("/auth/signup/verify", json={"token": new}).status_code == 200


def test_pre_registration_by_an_attacker_gives_them_nothing():
    """The attacker types the victim's address. Only the mailbox owner can finish sign-up."""
    with TestClient(app) as attacker, TestClient(app) as victim:
        assert request_signup(attacker, "victim@example.com").status_code == 202
        assert attacker.get("/auth/me").json() == {"user": None}
        assert login(attacker, "victim@example.com", "attacker guess!").status_code == 401
        token = token_from_mail()  # delivered to the victim's mailbox, never to the attacker
        assert victim.post("/auth/signup/verify", json={"token": token}).status_code == 200
        chosen = victim.post(
            "/auth/password/change", json={"new_password": "victims own passphrase"}
        )
        assert chosen.status_code == 200
        assert attacker.get("/auth/me").json() == {"user": None}


def test_signup_validation_and_limits():
    with TestClient(app) as client:
        assert request_signup(client, "nope").status_code == 422
        extra = client.post("/auth/signup", json={"email": "a@b.co", "password": PASSWORD})
        assert extra.status_code == 422  # no password is accepted at sign-up
        for i in range(9):  # the invalid address above already used one of the ten
            assert request_signup(client, f"u{i}@example.com").status_code == 202
        assert request_signup(client, "u11@example.com").status_code == 429


def test_per_address_signup_throttle_does_not_leak_either():
    with TestClient(app) as client:
        for _ in range(3):
            request_signup(client, "same@example.com")
        mail.outbox.clear()
        fourth = request_signup(client, "same@example.com")
        assert fourth.status_code == 202 and fourth.json() == {"status": "check_email"}
        assert mail.outbox == []


# --- sign-in ---


def test_login_logout_and_a_fresh_session_id_each_time():
    with TestClient(app) as client:
        user = sign_up(client, "real@example.com")
        first = client.cookies.get("maxx_session")
        client.post("/auth/logout")
        assert client.get("/auth/me").json() == {"user": None}
        done = login(client, "REAL@example.com")
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert client.cookies.get("maxx_session") not in (None, first)


def test_a_session_id_planted_before_login_is_ended():
    with TestClient(app) as victim, TestClient(app) as attacker:
        sign_up(attacker, "attacker@example.com")
        planted = attacker.cookies.get("maxx_session")
        sign_up(victim, "victim2@example.com")
        victim.post("/auth/logout")
        # Fixation: the attacker made the victim's browser send the attacker's own session id.
        done = login(victim, "victim2@example.com", cookie=f"maxx_session={planted}")
        assert done.status_code == 200
        assert victim.cookies.get("maxx_session") != planted
        assert attacker.get("/auth/me").json() == {"user": None}


def test_login_failures_are_generic_and_locked_out():
    with TestClient(app) as client:
        sign_up(client, "real@example.com")
        client.post("/auth/logout")
        wrong = login(client, "real@example.com", "nope-nope-nope")
        unknown = login(client, "ghost@example.com")
        assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
        for _ in range(7):
            login(client, "real@example.com", "nope-nope-nope")
        locked = login(client, "real@example.com")
        assert locked.status_code == 429 and "retry-after" in locked.headers


def test_email_link_sign_in_needs_no_password_and_reveals_nothing():
    with TestClient(app) as client, TestClient(app) as phone:
        user = sign_up(client, "link@example.com")
        client.post("/auth/logout")
        mail.outbox.clear()
        unknown = phone.post("/auth/login/link", json={"email": "ghost@example.com"})
        known = phone.post("/auth/login/link", json={"email": "link@example.com"})
        assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()
        assert [m["to"] for m in mail.outbox] == ["link@example.com"]
        token = token_from_mail()
        assert phone.post("/auth/login/link/verify", json={"token": "x" * 30}).status_code == 400
        done = phone.post("/auth/login/link/verify", json={"token": token})
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert phone.post("/auth/login/link/verify", json={"token": token}).status_code == 400


def test_unverified_addresses_cannot_use_email_links():
    with TestClient(app) as client:
        request_signup(client, "pending@example.com")
        mail.outbox.clear()
        client.post("/auth/login/link", json={"email": "pending@example.com"})
        assert mail.outbox == []


def test_secure_cookie_uses_the_host_prefix_over_https(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://maxx.example.com")
    with TestClient(app, base_url="https://testserver") as client:
        request_signup(client, "s@example.com")
        client.post("/auth/signup/verify", json={"token": token_from_mail()})
        cookie = next(iter(client.cookies.jar))
        assert cookie.name == "__Host-maxx_session" and cookie.secure and cookie.path == "/"


def test_sessions_end_by_absolute_lifetime_and_by_inactivity(monkeypatch):
    with TestClient(app) as client:
        sign_up(client)
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.session_idle_days * 86400 + 5)
        assert client.get("/auth/me").json() == {"user": None}  # idle too long
    with TestClient(app) as client:
        sign_up(client, "again@example.com")
        base = store.now()
        for day in range(1, settings.session_days):  # active often, so never idle...
            monkeypatch.setattr(store, "now", lambda day=day: base + day * 86400)
            assert client.get("/auth/me").json()["user"] is not None
        monkeypatch.setattr(store, "now", lambda: base + settings.session_days * 86400 + 5)
        assert client.get("/auth/me").json() == {"user": None}  # ...but the absolute cap ends it


# --- recovery ---


def test_password_reset_flow_revokes_sessions_and_cannot_be_replayed():
    with TestClient(app) as client:
        sign_up(client, "forgot@example.com")
        mail.outbox.clear()
        unknown = client.post("/auth/password/forgot", json={"email": "ghost@example.com"})
        known = client.post("/auth/password/forgot", json={"email": "Forgot@example.com"})
        assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()
        assert [m["to"] for m in mail.outbox] == ["forgot@example.com"]
        token = token_from_mail()
        weak = client.post("/auth/password/reset", json={"token": token, "password": "short"})
        assert weak.status_code == 422
        done = client.post("/auth/password/reset", json={"token": token, "password": OTHER})
        assert done.status_code == 200
        assert client.get("/auth/me").json() == {"user": None}
        replay = client.post("/auth/password/reset", json={"token": token, "password": OTHER + "!"})
        assert replay.status_code == 400
        assert login(client, "forgot@example.com").status_code == 401
        assert login(client, "forgot@example.com", OTHER).status_code == 200
        assert any("password was reset" in m["text"] for m in mail.outbox)  # the owner is told


def test_breached_passwords_are_refused_without_sending_them(monkeypatch):
    monkeypatch.setattr(settings, "hibp_enabled", True)
    seen = []
    digest = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()

    def handler(request):
        seen.append(str(request.url))
        assert request.headers["add-padding"] == "true"
        padding = "AAAA0000000000000000000000000000000:0"
        return httpx.Response(200, text=f"{padding}\r\n{digest[5:]}:7\r\n")

    monkeypatch.setattr(breach, "transport", httpx.MockTransport(handler))
    with TestClient(app) as client:
        request_signup(client, "b@example.com")
        client.post("/auth/signup/verify", json={"token": token_from_mail()})
        refused = client.post("/auth/password/change", json={"new_password": PASSWORD})
        assert refused.status_code == 422 and "breach" in refused.json()["detail"]
        assert len(seen) == 1 and seen[0].endswith("/range/" + digest[:5])
        assert PASSWORD not in seen[0] and digest[5:] not in seen[0]  # only the prefix leaves
        clean = httpx.MockTransport(lambda r: httpx.Response(200, text=""))
        monkeypatch.setattr(breach, "transport", clean)
        assert (
            client.post("/auth/password/change", json={"new_password": PASSWORD}).status_code == 200
        )


def test_the_breach_check_never_blocks_people_when_the_service_is_down(monkeypatch):
    monkeypatch.setattr(settings, "hibp_enabled", True)

    def down(request):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(breach, "transport", httpx.MockTransport(down))
    with TestClient(app) as client:
        sign_up(client, "offline@example.com")
        change = {"current_password": PASSWORD, "new_password": OTHER}
        assert client.post("/auth/password/change", json=change).status_code == 200


def test_legacy_email_verification_still_works_and_is_single_use():
    with TestClient(app) as client:
        user = sign_up(client, "legacy@example.com")
        store.update_user(user["id"], email_verified=False)
        assert client.post("/auth/email/resend").status_code == 202
        token = token_from_mail(path="/verify-email")
        assert client.post("/auth/email/verify", json={"token": token}).status_code == 200
        assert client.post("/auth/email/verify", json={"token": token}).status_code == 400


# --- freshness and sensitive changes ---


def test_sensitive_changes_demand_a_recent_identity_check(monkeypatch):
    with TestClient(app) as client:
        sign_up(client, "fresh@example.com")
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        change = {"current_password": PASSWORD, "new_password": OTHER}
        stale = client.post("/auth/password/change", json=change)
        assert stale.status_code == 403 and stale.json()["code"] == "reauth_required"
        assert client.get("/auth/sessions").status_code == 200  # reading is not sensitive
        wrong = client.post("/auth/reauth", json={"method": "password", "password": "not-the-one"})
        assert wrong.status_code == 403
        right = client.post("/auth/reauth", json={"method": "password", "password": PASSWORD})
        assert right.status_code == 200
        assert client.post("/auth/password/change", json=change).status_code == 200


def test_people_without_a_password_can_reauthenticate_by_emailed_code(monkeypatch):
    with TestClient(app) as client:
        request_signup(client, "nopw@example.com")
        client.post("/auth/signup/verify", json={"token": token_from_mail()})
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        methods = client.get("/auth/reauth/methods").json()
        assert methods == {"password": False, "totp": False, "passkey": False, "email_code": True}
        assert client.post("/auth/sessions/revoke-others").json()["code"] == "reauth_required"
        assert client.post("/auth/reauth/email/send").status_code == 202
        code = re.search(r"code is (\d{6})", mail.outbox[-1]["text"]).group(1)
        bad = client.post("/auth/reauth", json={"method": "email_code", "code": "000000"})
        assert bad.status_code == 403
        good = client.post("/auth/reauth", json={"method": "email_code", "code": code})
        assert good.status_code == 200
        again = client.post("/auth/reauth", json={"method": "email_code", "code": code})
        assert again.status_code == 403  # one use only
        assert client.post("/auth/sessions/revoke-others").status_code == 200


def test_change_password_signs_out_other_devices_and_rotates_this_one():
    with TestClient(app) as laptop, TestClient(app) as phone:
        sign_up(laptop, "pw@example.com")
        login(phone, "pw@example.com")
        before = laptop.cookies.get("maxx_session")
        wrong = laptop.post(
            "/auth/password/change",
            json={"current_password": "not-it-at-all", "new_password": OTHER},
        )
        assert wrong.status_code == 403
        ok = laptop.post(
            "/auth/password/change", json={"current_password": PASSWORD, "new_password": OTHER}
        )
        assert ok.status_code == 200 and ok.json()["signed_out_elsewhere"] == 1
        assert (
            laptop.cookies.get("maxx_session") != before and laptop.get("/auth/me").json()["user"]
        )
        assert phone.get("/auth/me").json() == {"user": None}
        assert any("password was changed" in m["text"] for m in mail.outbox)


def test_sessions_list_and_revoke():
    with TestClient(app) as laptop, TestClient(app) as phone:
        sign_up(laptop, "s@example.com")
        login(phone, "s@example.com", **{"user-agent": "Maxx Test Phone"})
        listing = laptop.get("/auth/sessions").json()["sessions"]
        assert len(listing) == 2 and sum(s["current"] for s in listing) == 1
        other = next(s for s in listing if not s["current"])
        current = next(s for s in listing if s["current"])
        assert other["user_agent"] == "Maxx Test Phone"
        assert laptop.delete(f"/auth/sessions/{current['id']}").status_code == 409
        assert laptop.delete("/auth/sessions/not-a-real-one!").status_code == 404
        assert laptop.delete(f"/auth/sessions/{other['id']}").status_code == 204
        assert phone.get("/auth/me").json() == {"user": None}


def test_profile_update_and_login_required():
    with TestClient(app) as client:
        assert client.patch("/auth/me", json={"display_name": "x"}).status_code == 401
        sign_up(client)
        renamed = client.patch("/auth/me", json={"display_name": "  Rae   Lee "})
        assert renamed.json()["user"]["display_name"] == "Rae Lee"
        assert client.patch("/auth/me", json={"display_name": "   "}).status_code == 422


# --- security activity and alerts ---


def test_activity_trail_and_new_device_alert():
    with TestClient(app) as laptop, TestClient(app) as stranger:
        sign_up(laptop, "trail@example.com")
        laptop.post("/auth/logout")
        login(laptop, "trail@example.com", **{"user-agent": "Laptop/1"})
        mail.outbox.clear()
        login(
            stranger,
            "trail@example.com",
            **{"user-agent": "Unfamiliar/9", "x-forwarded-for": "203.0.113.7"},
        )
        assert any("new device" in m["subject"].lower() for m in mail.outbox)
        feed = stranger.get("/auth/activity").json()["events"]
        kinds = [e["kind"] for e in feed]
        assert "new_device" in kinds and "login" in kinds and "signup" in kinds
        assert next(e for e in feed if e["kind"] == "new_device")["alert"] is True
        assert "203.0.113.7" not in str(feed)  # only the network is kept, never the full address
        assert any(e["network"] == "203.0.113.0/24" for e in feed)


def test_failed_logins_are_recorded_for_the_owner_only():
    with TestClient(app) as client:
        sign_up(client, "watch@example.com")
        client.post("/auth/logout")
        login(client, "watch@example.com", "wrong-wrong-wrong")
        login(client, "ghost@example.com", "wrong-wrong-wrong")
        login(client, "watch@example.com")
        kinds = [e["kind"] for e in client.get("/auth/activity").json()["events"]]
        assert kinds.count("login_failed") == 1


# --- request-level hardening ---


def test_cross_site_writes_are_blocked_but_same_site_works():
    with TestClient(app) as client:
        assert request_signup(client, "c@example.com").status_code == 202
        evil = client.post(
            "/auth/signup",
            json={"email": "d@example.com"},
            headers={"origin": "https://evil.example"},
        )
        assert evil.status_code == 403
        referer = client.post("/auth/logout", headers={"referer": "https://evil.example/x"})
        assert referer.status_code == 403
        good = client.post(
            "/auth/signup",
            json={"email": "e@example.com"},
            headers={"origin": "http://localhost:3001"},
        )
        assert good.status_code == 202


def test_fetch_metadata_blocks_cross_site_state_changes():
    with TestClient(app) as client:
        for site in ("cross-site", "same-site"):
            blocked = client.post(
                "/auth/signup", json={"email": "f@example.com"}, headers={"sec-fetch-site": site}
            )
            assert blocked.status_code == 403, site
        for site in ("same-origin", "none"):
            ok = client.post(
                "/auth/signup",
                json={"email": f"{site}@example.com"},
                headers={"sec-fetch-site": site},
            )
            assert ok.status_code == 202
        assert client.get("/auth/me", headers={"sec-fetch-site": "cross-site"}).status_code == 200


def test_state_changing_requests_must_be_json_and_small():
    with TestClient(app) as client:
        form = client.post(
            "/auth/signup",
            content="email=a%40b.co",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert form.status_code == 415
        text = client.post("/auth/signup", content="{}", headers={"content-type": "text/plain"})
        assert text.status_code == 415
        big = client.post(
            "/auth/signup",
            content=b'{"email":"' + b"a" * 70000 + b'"}',
            headers={"content-type": "application/json"},
        )
        assert big.status_code == 413


def test_every_response_has_security_headers_and_account_responses_are_not_cached():
    with TestClient(app) as client:
        for path in ("/health", "/auth/me", "/auth/providers", "/blocs"):
            headers = client.get(path).headers
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert headers["referrer-policy"] == "no-referrer"
            assert "frame-ancestors 'none'" in headers["content-security-policy"]
            assert headers["cross-origin-resource-policy"] == "same-origin"
            assert headers["x-request-id"]
        assert client.get("/auth/me").headers["cache-control"] == "no-store"
        assert "strict-transport-security" not in client.get("/health").headers


def test_hsts_is_sent_only_over_https(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://maxx.example.com")
    with TestClient(app) as client:
        assert "max-age=63072000" in client.get("/health").headers["strict-transport-security"]


def test_a_global_request_budget_stops_floods(monkeypatch):
    monkeypatch.setattr(settings, "api_rate_per_minute", 20)
    with TestClient(app) as client:
        codes = [client.get("/auth/providers").status_code for _ in range(25)]
        assert codes[:20] == [200] * 20 and set(codes[20:]) == {429}
        assert client.get("/health").status_code == 200  # liveness is never throttled


def test_no_cross_origin_resource_sharing_is_ever_granted():
    with TestClient(app) as client:
        preflight = client.options(
            "/auth/me",
            headers={"origin": "https://evil.example", "access-control-request-method": "GET"},
        )
        assert "access-control-allow-origin" not in preflight.headers
        actual = client.get("/auth/me", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in actual.headers


def test_captcha_is_enforced_when_configured_and_failed_logins_escalate(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_site_key", "site")
    monkeypatch.setattr(settings, "turnstile_secret", "secret")
    calls = []

    def handler(request):
        calls.append(request.content.decode())
        return httpx.Response(200, json={"success": b"good-token" in request.content})

    monkeypatch.setattr(captcha, "transport", httpx.MockTransport(handler))
    with TestClient(app) as client:
        offered = client.get("/auth/providers").json()["captcha"]
        assert offered == {"provider": "turnstile", "site_key": "site"}
        missing = client.post("/auth/signup", json={"email": "cap@example.com"})
        assert missing.status_code == 400 and missing.json()["code"] == "captcha_required"
        forged = client.post("/auth/signup", json={"email": "cap@example.com", "captcha": "bad"})
        assert forged.status_code == 400
        ok = client.post("/auth/signup", json={"email": "cap@example.com", "captcha": "good-token"})
        assert ok.status_code == 202
        assert "secret=secret" in calls[-1] and "response=good-token" in calls[-1]
        # Sign-in only asks after repeated misses, so normal people are never challenged.
        for _ in range(3):
            assert login(client, "cap@example.com", "nope-nope-nope").status_code == 401
        escalated = login(client, "cap@example.com", "nope-nope-nope")
        assert escalated.status_code == 400 and escalated.json()["code"] == "captcha_required"


def test_a_captcha_service_outage_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "turnstile_site_key", "site")
    monkeypatch.setattr(settings, "turnstile_secret", "secret")

    def down(request):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(captcha, "transport", httpx.MockTransport(down))
    with TestClient(app) as client:
        blocked = client.post("/auth/signup", json={"email": "x@example.com", "captcha": "t"})
        assert blocked.status_code == 400


# --- Blocs, ownership and privacy ---


def test_joining_uses_the_session_and_hides_other_accounts(runtime):
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anonymous:
        alice_user = sign_up(alice, "alice@example.com")
        bob_user = sign_up(bob, "bob@example.com")
        spoof = alice.post("/blocs/demo-success/join", json={"user_id": "x", "max_price": "150"})
        assert spoof.status_code == 422
        assert alice.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 200
        assert bob.post("/blocs/demo-success/join", json={"max_price": "140"}).status_code == 200
        for viewer, mine in ((alice, "150.00"), (bob, "140.00"), (anonymous, None)):
            body = viewer.get("/blocs/demo-success").json()
            text = str(body)
            assert alice_user["id"] not in text and bob_user["id"] not in text
            assert "alice@example.com" not in text
            ours = [m for m in body["members"] if m["user_id"] == "me"]
            assert (len(ours) == 1 and float(ours[0]["max_price"]) == float(mine or 0)) or (
                mine is None and not ours
            )
        members = anonymous.get("/blocs/demo-success").json()["members"]
        assert all(m["user_id"] == m["id"] for m in members)


def test_only_members_or_the_owner_may_close_a_bloc(runtime):
    with TestClient(app) as owner, TestClient(app) as stranger, TestClient(app) as anonymous:
        sign_up(owner, "owner@example.com")
        sign_up(stranger, "stranger@example.com")
        assert anonymous.post("/blocs/demo-success/start").status_code == 401
        assert stranger.post("/blocs/demo-success/start").status_code == 403
        assert owner.post("/blocs/demo-success/join", json={"max_price": "150"}).status_code == 200
        assert stranger.post("/blocs/demo-success/start").status_code == 403
        assert owner.post("/blocs/demo-success/start").status_code == 202


def test_creating_a_bloc_requires_an_account_and_records_the_owner(runtime):
    body = {"title": "My exact gadget, black", "typical_price": "100", "confirmed_variant": True}
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as anonymous:
        assert anonymous.post("/blocs", json=body).status_code == 401
        sign_up(owner, "maker@example.com")
        created = owner.post("/blocs", json=body)
        assert created.status_code == 201 and created.json()["viewer_is_owner"] is True
        bloc_id = created.json()["id"]
        assert "owner_id" not in created.text
        sign_up(other, "other@example.com")
        assert other.get(f"/blocs/{bloc_id}").json()["viewer_is_owner"] is False
        assert owner.post(f"/blocs/{bloc_id}/start").status_code == 202


def test_my_blocs_lists_only_my_participation(runtime):
    with TestClient(app) as me, TestClient(app) as other:
        assert me.get("/me/blocs").status_code == 401
        sign_up(me, "me@example.com")
        sign_up(other, "o@example.com")
        assert me.get("/me/blocs").json() == []
        me.post("/blocs/demo-success/join", json={"max_price": "150"})
        other.post("/blocs/demo-failure/join", json={"max_price": "150"})
        assert [b["id"] for b in me.get("/me/blocs").json()] == ["demo-success"]


def test_demo_reset_is_limited_to_admins_when_configured(runtime, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    with TestClient(app) as boss, TestClient(app) as member:
        sign_up(boss, "boss@example.com")
        sign_up(member, "member@example.com")
        assert member.post("/demo/reset").status_code == 403
        assert boss.post("/demo/reset").status_code == 200  # signing up verified the mailbox


def test_scan_allowance_is_enforced_per_address(monkeypatch):
    monkeypatch.setattr(settings, "scan_rate_anonymous_per_hour", 2)
    with TestClient(app) as client:

        def send():
            posted = client.post(
                "/scan", content=b"not-an-image", headers={"content-type": "image/png"}
            )
            return posted.status_code

        assert [send(), send(), send()] == [422, 422, 429]


def test_forged_forwarded_for_does_not_open_new_allowances(monkeypatch):
    monkeypatch.setattr(settings, "scan_rate_anonymous_per_hour", 2)
    with TestClient(app) as client:

        def send(forged):
            # The browser controls the leftmost entries; the proxy appends the real address last.
            posted = client.post(
                "/scan",
                content=b"not-an-image",
                headers={"content-type": "image/png", "x-forwarded-for": f"{forged}, 203.0.113.9"},
            )
            return posted.status_code

        assert [send("1.1.1.1"), send("2.2.2.2"), send("3.3.3.3")] == [422, 422, 429]


def test_live_streams_are_capped_per_address(monkeypatch):
    from fastapi import HTTPException

    from maxx import hardening

    monkeypatch.setattr(settings, "stream_connections_per_ip", 1)
    with hardening.streams.slot("1.2.3.4", "demo-success"):
        with pytest.raises(HTTPException) as caught:
            with hardening.streams.slot("1.2.3.4", "demo-failure"):
                pass
        assert caught.value.status_code == 429
        with hardening.streams.slot("5.6.7.8", "demo-success"):
            pass  # a different address is unaffected
    with hardening.streams.slot("1.2.3.4", "demo-success"):
        pass  # and the slot frees on exit


def test_stream_slot_frees_when_the_client_leaves_before_the_first_event(runtime, monkeypatch):
    import asyncio

    from maxx import hardening

    from maxx.negotiate import routes

    monkeypatch.setattr(settings, "stream_connections_per_ip", 1)
    request = type("Req", (), {"headers": {}, "client": type("C", (), {"host": "9.9.9.9"})()})()
    response = asyncio.run(routes.stream_bloc("demo-success", request, runtime, 0))

    async def gone(message):
        raise OSError("client disconnected")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(Exception):  # Starlette reports the failed send as ClientDisconnect
        asyncio.run(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, gone))
    assert "9.9.9.9" not in hardening.streams.by_ip


def test_delete_account_releases_commitments_and_removes_the_login(runtime):
    with TestClient(app) as client:
        user = sign_up(client, "bye@example.com")
        client.post("/blocs/demo-success/join", json={"max_price": "150"})
        assert client.post("/auth/me/delete", json={"confirm": "yes"}).status_code == 422
        done = client.post("/auth/me/delete", json={"confirm": "delete my account"})
        assert done.status_code == 204
        assert client.get("/auth/me").json() == {"user": None}
        assert login(client, "bye@example.com").status_code == 401
        stored = runtime.store.get("demo-success")
        assert user["id"] not in stored.model_dump_json()
        released = [m for m in stored.members if m.user_id == "deleted-account"]
        assert len(released) == 1 and released[0].status == "LEFT"
        assert store.list_events(user["id"]) == []  # the trail goes with the account


def test_deleting_an_account_requires_a_fresh_identity_check(runtime, monkeypatch):
    with TestClient(app) as client:
        sign_up(client, "stale@example.com")
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        gone = client.post("/auth/me/delete", json={"confirm": "delete my account"})
        assert gone.status_code == 403 and gone.json()["code"] == "reauth_required"


# --- production configuration guard ---


def test_production_refuses_to_start_with_insecure_settings(monkeypatch):
    from maxx import hardening
    from maxx import secrets as vault

    monkeypatch.setattr(settings, "environment", "production")
    vault.reset()
    problems = " | ".join(hardening.configuration_problems())
    for expected in ("https", "SECRET_KEY", "DATABASE_URL", "EMAIL_MODE", "ALLOWED_HOSTS"):
        assert expected in problems, expected
    monkeypatch.setattr(settings, "public_base_url", "https://maxx.example.com")
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://app:strong@db/maxx")
    monkeypatch.setattr(settings, "email_mode", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "allowed_hosts", "maxx.example.com")
    monkeypatch.setattr(settings, "seller_review", "manual")
    vault.reset()
    assert hardening.configuration_problems() == []
    monkeypatch.setattr(settings, "docs_enabled", True)
    assert any("DOCS_ENABLED" in p for p in hardening.configuration_problems())
    vault.reset()


def test_secrets_are_sealed_per_purpose_and_tamper_evident():
    from cryptography.exceptions import InvalidTag

    from maxx import secrets as vault

    sealed = vault.encrypt("JBSWY3DPEHPK3PXP", "totp")
    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert vault.decrypt(sealed, "totp") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(InvalidTag):
        vault.decrypt(sealed, "other-purpose")
    with pytest.raises(InvalidTag):
        vault.decrypt(sealed[:-4] + "AAAA", "totp")
