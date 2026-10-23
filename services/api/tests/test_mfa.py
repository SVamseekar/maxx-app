"""Two-step verification: enrolment, sign-in, replay, brute force, recovery, remembered browsers."""

import re

from fastapi.testclient import TestClient

from maxx import secrets as vault
from maxx.auth import mail, mfa, store
from maxx.config import settings
from maxx.main import app
from tests.conftest import sign_up
from tests.test_auth import PASSWORD, login, request_signup, token_from_mail


def enrol(client, email="mfa@example.com", **kwargs):
    """Sign up, turn on two-step verification, and return (seed, recovery codes)."""
    user = sign_up(client, email, **kwargs)
    setup = client.post("/auth/mfa/totp/setup")
    assert setup.status_code == 200, setup.text
    seed = setup.json()["secret"]
    enabled = client.post("/auth/mfa/totp/enable", json={"code": mfa.code_at(seed)})
    assert enabled.status_code == 200, enabled.text
    return user, seed, enabled.json()["recovery_codes"]


def later_code(seed, steps=1):
    """A valid code from a later 30-second window than any already used."""
    import time

    return mfa.code_at(seed, time.time() + 30 * steps)


# --- the algorithm ---


def test_totp_matches_the_rfc_6238_test_vectors():
    seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert mfa._code(seed, 59 // 30) == "287082"
    assert mfa._code(seed, 1111111109 // 30) == "081804"
    assert mfa._code(seed, 1234567890 // 30) == "005924"
    assert mfa.match(seed, "287 082", now=59) == 1  # spaces and a dash are tolerated
    assert mfa.match(seed, "287082", now=59 + 30) == 1  # one window of clock drift
    assert mfa.match(seed, "287082", now=59 + 90) is None  # but no more
    assert mfa.match(seed, "12345", now=59) is None and mfa.match(seed, "abcdef", now=59) is None


def test_recovery_codes_are_unambiguous_and_hashed():
    codes = mfa.new_recovery_codes()
    assert len(codes) == len(set(codes)) == 10
    assert all(re.fullmatch(r"[a-z2-9]{5}-[a-z2-9]{5}", c) for c in codes)
    assert not any(ch in "ilo01" for c in codes for ch in c.replace("-", ""))
    assert mfa.recovery_hash(codes[0].upper()) == mfa.recovery_hash(codes[0].replace("-", " "))
    assert codes[0] not in mfa.recovery_hash(codes[0])


# --- enrolment ---


def test_enrolment_stores_the_seed_encrypted_and_alerts_the_owner():
    with TestClient(app) as laptop, TestClient(app) as phone:
        sign_up(laptop, "enrol@example.com")
        login(phone, "enrol@example.com")
        setup = laptop.post("/auth/mfa/totp/setup").json()
        assert setup["otpauth_uri"].startswith("otpauth://totp/Maxx:enrol%40example.com?secret=")
        assert "algorithm=SHA1&digits=6&period=30" in setup["otpauth_uri"]
        user = store.get_user_by_email("enrol@example.com")
        sealed, pending, enabled = store.totp_material(user.id)
        assert pending and not enabled and setup["secret"] not in pending  # sealed at rest
        assert vault.decrypt(pending, "totp") == setup["secret"]
        wrong = laptop.post("/auth/mfa/totp/enable", json={"code": "000000"})
        assert wrong.status_code == 422
        mail.outbox.clear()
        done = laptop.post("/auth/mfa/totp/enable", json={"code": mfa.code_at(setup["secret"])})
        assert done.status_code == 200 and len(done.json()["recovery_codes"]) == 10
        assert laptop.get("/auth/me").json()["user"]["totp_enabled"] is True
        assert phone.get("/auth/me").json() == {"user": None}  # every other sign-in ended
        assert any("two-step" in m["text"].lower() for m in mail.outbox)
        assert laptop.post("/auth/mfa/totp/setup").status_code == 409  # already on


def test_enrolment_needs_a_fresh_identity_check(monkeypatch):
    with TestClient(app) as client:
        sign_up(client, "stale-mfa@example.com")
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        assert client.post("/auth/mfa/totp/setup").json()["code"] == "reauth_required"


# --- signing in ---


def test_password_alone_no_longer_signs_in_and_the_second_step_does():
    with TestClient(app) as laptop, TestClient(app) as client:
        user, seed, _ = enrol(laptop, "login-mfa@example.com")
        first = login(client, "login-mfa@example.com")
        assert first.status_code == 200 and first.json()["mfa_required"] is True
        assert "set-cookie" not in first.headers and client.get("/auth/me").json() == {"user": None}
        token = first.json()["mfa_token"]
        wrong = client.post("/auth/login/mfa", json={"mfa_token": token, "code": "000000"})
        assert wrong.status_code == 401
        code = later_code(seed)  # enrolment already used this window's code
        done = client.post("/auth/login/mfa", json={"mfa_token": token, "code": code})
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert client.get("/auth/me").json()["user"]["id"] == user["id"]
        reuse = client.post("/auth/login/mfa", json={"mfa_token": token, "code": code})
        assert reuse.status_code == 401


def test_a_code_cannot_be_used_twice_even_inside_its_window():
    with TestClient(app) as laptop, TestClient(app) as client, TestClient(app) as thief:
        _, seed, _ = enrol(laptop, "replay@example.com")  # enabling used this window's code
        token = login(client, "replay@example.com").json()["mfa_token"]
        replayed = client.post(
            "/auth/login/mfa", json={"mfa_token": token, "code": mfa.code_at(seed)}
        )
        assert replayed.status_code == 401
        fresh = client.post("/auth/login/mfa", json={"mfa_token": token, "code": later_code(seed)})
        assert fresh.status_code == 200
        # Someone who watched that code being typed cannot reuse it.
        stolen = login(thief, "replay@example.com").json()["mfa_token"]
        again = thief.post("/auth/login/mfa", json={"mfa_token": stolen, "code": later_code(seed)})
        assert again.status_code == 401


def test_wrong_codes_burn_the_pending_sign_in_and_lock_the_account_out_briefly():
    with TestClient(app) as laptop, TestClient(app) as client:
        _, seed, _ = enrol(laptop, "brute@example.com")
        token = login(client, "brute@example.com").json()["mfa_token"]
        results = [
            client.post(
                "/auth/login/mfa", json={"mfa_token": token, "code": f"{i:06d}"}
            ).status_code
            for i in range(5)
        ]
        assert results == [401] * 5
        burnt = client.post("/auth/login/mfa", json={"mfa_token": token, "code": later_code(seed)})
        assert burnt.status_code == 401  # even the right code: this sign-in is over
        events = [
            e.kind for e in store.list_events(store.get_user_by_email("brute@example.com").id)
        ]
        assert events.count("mfa_failed") >= 5


def test_a_forged_or_unrelated_mfa_token_is_useless():
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/login/mfa", json={"mfa_token": "x" * 40, "code": "123456"}
            ).status_code
            == 401
        )


def test_email_link_sign_in_also_asks_for_the_second_step():
    with TestClient(app) as laptop, TestClient(app) as client:
        user, seed, _ = enrol(laptop, "link-mfa@example.com")
        client.post("/auth/login/link", json={"email": "link-mfa@example.com"})
        link = client.post("/auth/login/link/verify", json={"token": token_from_mail()})
        assert link.json()["mfa_required"] is True and client.get("/auth/me").json() == {
            "user": None
        }
        done = client.post(
            "/auth/login/mfa",
            json={"mfa_token": link.json()["mfa_token"], "code": later_code(seed)},
        )
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]


# --- recovery codes ---


def test_a_recovery_code_works_once_and_raises_an_alert():
    with TestClient(app) as laptop, TestClient(app) as client:
        user, _, codes = enrol(laptop, "recover@example.com")
        token = login(client, "recover@example.com").json()["mfa_token"]
        mail.outbox.clear()
        typed = codes[0].upper().replace("-", " ")  # forgiving about case and separators
        done = client.post("/auth/login/mfa", json={"mfa_token": token, "code": typed})
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert any("recovery code" in m["text"].lower() for m in mail.outbox)
        assert store.recovery_codes_left(user["id"]) == 9
        again = login(TestClient(app), "recover@example.com").json()["mfa_token"]
        reuse = TestClient(app).post("/auth/login/mfa", json={"mfa_token": again, "code": codes[0]})
        assert reuse.status_code == 401


def test_regenerating_codes_invalidates_the_old_set():
    with TestClient(app) as client:
        _, seed, old = enrol(client, "regen@example.com")
        new = client.post("/auth/mfa/recovery/regenerate", json={"code": later_code(seed)})
        assert new.status_code == 200 and set(new.json()["recovery_codes"]).isdisjoint(old)
        assert client.get("/auth/security").json()["recovery_codes_left"] == 10
        user = store.get_user_by_email("regen@example.com")
        assert not store.use_recovery_code(user.id, mfa.recovery_hash(old[0]))
        assert store.use_recovery_code(user.id, mfa.recovery_hash(new.json()["recovery_codes"][0]))


# --- remembered browsers ---


def test_a_remembered_browser_skips_the_second_step_until_something_changes():
    with TestClient(app) as laptop, TestClient(app) as home:
        user, seed, _ = enrol(laptop, "trust@example.com")
        token = login(home, "trust@example.com").json()["mfa_token"]
        home.post(
            "/auth/login/mfa", json={"mfa_token": token, "code": later_code(seed), "remember": True}
        )
        assert home.cookies.get("maxx_trusted")
        assert store.count_trusted_devices(user["id"]) == 1
        home.post("/auth/logout")
        direct = login(home, "trust@example.com")
        assert "mfa_required" not in direct.json() and home.get("/auth/me").json()["user"]
        # A different browser is not trusted, and neither is this one once the password changes.
        assert login(TestClient(app), "trust@example.com").json()["mfa_required"] is True
        change = {"current_password": PASSWORD, "new_password": "a brand new passphrase!"}
        assert laptop.post("/auth/password/change", json=change).status_code == 200
        home.post("/auth/logout")
        assert (
            login(home, "trust@example.com", "a brand new passphrase!").json()["mfa_required"]
            is True
        )


def test_a_trusted_browser_token_cannot_be_used_for_another_account():
    with TestClient(app) as a, TestClient(app) as b, TestClient(app) as victim:
        _, seed_a, _ = enrol(a, "owner-a@example.com")
        _, seed_b, _ = enrol(b, "owner-b@example.com")
        home = TestClient(app)
        token = login(home, "owner-a@example.com").json()["mfa_token"]
        home.post(
            "/auth/login/mfa",
            json={"mfa_token": token, "code": later_code(seed_a), "remember": True},
        )
        borrowed = home.cookies.get("maxx_trusted")
        victim.cookies.set("maxx_trusted", borrowed)
        attempt = login(victim, "owner-b@example.com", cookie=f"maxx_trusted={borrowed}")
        assert attempt.json()["mfa_required"] is True


# --- turning it off ---


def test_turning_it_off_needs_a_valid_code_and_forgets_everything():
    with TestClient(app) as client:
        user, seed, _ = enrol(client, "off@example.com")
        assert client.post("/auth/mfa/totp/disable", json={"code": "000000"}).status_code == 403
        mail.outbox.clear()
        assert (
            client.post("/auth/mfa/totp/disable", json={"code": later_code(seed)}).status_code
            == 200
        )
        assert any("turned off" in m["text"].lower() for m in mail.outbox)
        assert store.totp_material(user["id"]) == (None, None, False)
        assert (
            store.recovery_codes_left(user["id"]) == 0
            and store.count_trusted_devices(user["id"]) == 0
        )
        client.post("/auth/logout")
        assert "mfa_required" not in login(client, "off@example.com").json()


def test_unverified_accounts_cannot_enrol_anything_before_signing_in():
    with TestClient(app) as client:
        request_signup(client, "anon@example.com")
        assert client.post("/auth/mfa/totp/setup").status_code == 401
