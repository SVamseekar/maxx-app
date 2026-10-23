"""Passkeys (WebAuthn) against a software authenticator building real attestations."""

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from maxx.auth import mail, store
from maxx.config import settings
from maxx.main import app
from tests.conftest import sign_up
from tests.test_auth import PASSWORD, login, request_signup
from tests.test_mfa import enrol

ORIGIN = "http://localhost:3001"
RP_ID = "localhost"


def b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class SoftKey:
    """A minimal platform authenticator: ES256 keys, packed counters, 'none' attestation."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0
        self.user_handle = b""

    def _client_data(self, kind, challenge, origin):
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}
        ).encode()

    def create(self, options, origin=ORIGIN, rp_id=RP_ID, flags=0x45):
        public = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big")}
        )
        data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.counter)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + cose
        )
        self.user_handle = unb64(options["user"]["id"])
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": data})
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "attestationObject": b64(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def get(self, options, origin=ORIGIN, rp_id=RP_ID, flags=0x05, bump=1, key=None):
        self.counter += bump
        auth = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.counter)
        )
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signed = auth + hashlib.sha256(client_data).digest()
        signature = (key or self.key).sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(auth),
                "signature": b64(signature),
                "userHandle": b64(self.user_handle),
            },
            "clientExtensionResults": {},
        }


def register(client, device=None, name="Test laptop", **create):
    device = device or SoftKey()
    started = client.post("/auth/passkeys/register/options")
    assert started.status_code == 200, started.text
    body = started.json()
    done = client.post(
        "/auth/passkeys/register/verify",
        json={
            "challenge_id": body["challenge_id"],
            "credential": device.create(body["options"], **create),
            "name": name,
        },
    )
    return device, started, done


def passkey_login(client, device, **get):
    started = client.post("/auth/passkeys/login/options").json()
    return client.post(
        "/auth/passkeys/login/verify",
        json={
            "challenge_id": started["challenge_id"],
            "credential": device.get(started["options"], **get),
        },
    )


# --- registration ---


def test_registering_a_passkey_requires_user_verification_and_a_resident_key():
    with TestClient(app) as client:
        sign_up(client, "pk@example.com")
        device, started, done = register(client)
        options = started.json()["options"]
        assert options["rp"] == {"name": "Maxx", "id": "localhost"}
        assert options["authenticatorSelection"]["residentKey"] == "required"
        assert options["authenticatorSelection"]["userVerification"] == "required"
        assert options["attestation"] == "none" and len(options["challenge"]) >= 43
        assert done.status_code == 200 and done.json() == {"status": "added", "name": "Test laptop"}
        listing = client.get("/auth/security").json()["passkeys"]
        assert len(listing) == 1 and listing[0]["name"] == "Test laptop"
        assert any("passkey was added" in m["text"] for m in mail.outbox)
        assert client.get("/auth/me").json()["user"]["passkeys"] == 1


def test_the_same_authenticator_cannot_register_twice_and_is_excluded_from_new_requests():
    with TestClient(app) as client:
        sign_up(client, "dup-pk@example.com")
        device, _, _ = register(client)
        again = client.post("/auth/passkeys/register/options").json()["options"]
        assert [c["id"] for c in again["excludeCredentials"]] == [b64(device.credential_id)]


def test_bad_registrations_are_rejected():
    with TestClient(app) as client:
        sign_up(client, "bad-pk@example.com")
        for label, create in {
            "wrong origin": {"origin": "https://evil.example"},
            "wrong relying party": {"rp_id": "evil.example"},
            "no user verification": {"flags": 0x41},
        }.items():
            _, _, done = register(client, **create)
            assert done.status_code == 400, label
        started = client.post("/auth/passkeys/register/options").json()
        device = SoftKey()
        ok = {
            "challenge_id": started["challenge_id"],
            "credential": device.create(started["options"]),
            "name": "x",
        }
        assert client.post("/auth/passkeys/register/verify", json=ok).status_code == 200
        assert (
            client.post("/auth/passkeys/register/verify", json=ok).status_code == 400
        )  # challenge is single use
        assert client.get("/auth/security").json()["passkeys"][0]["name"] == "x"


def test_a_registration_challenge_belongs_to_the_account_that_asked():
    with TestClient(app) as alice, TestClient(app) as mallory:
        sign_up(alice, "alice-pk@example.com")
        sign_up(mallory, "mallory-pk@example.com")
        started = alice.post("/auth/passkeys/register/options").json()
        stolen = {
            "challenge_id": started["challenge_id"],
            "credential": SoftKey().create(started["options"]),
            "name": "x",
        }
        assert mallory.post("/auth/passkeys/register/verify", json=stolen).status_code == 400


def test_registration_needs_a_fresh_identity_check(monkeypatch):
    with TestClient(app) as client:
        sign_up(client, "stale-pk@example.com")
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        assert client.post("/auth/passkeys/register/options").json()["code"] == "reauth_required"


# --- signing in ---


def test_signing_in_with_a_passkey_needs_no_username_or_password():
    with TestClient(app) as laptop, TestClient(app) as client:
        user = sign_up(laptop, "pk-login@example.com")
        device, _, _ = register(laptop)
        done = passkey_login(client, device)
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert client.get("/auth/me").json()["user"]["id"] == user["id"]
        kinds = [e.kind for e in store.list_events(user["id"])]
        assert "login_passkey" in kinds
        used = client.get("/auth/security").json()["passkeys"][0]
        assert used["last_used_at"] is not None
        assert store.get_passkey(b64(device.credential_id)).sign_count == device.counter


def test_a_passkey_also_satisfies_two_step_verification():
    with TestClient(app) as laptop, TestClient(app) as client:
        user, _, _ = enrol(laptop, "pk-mfa@example.com")
        device, _, _ = register(laptop)
        done = passkey_login(client, device)
        assert done.status_code == 200 and "mfa_required" not in done.json()
        assert done.json()["user"]["id"] == user["id"]


def test_assertions_that_do_not_check_out_are_refused():
    with TestClient(app) as laptop, TestClient(app) as client:
        sign_up(laptop, "pk-refuse@example.com")
        device, _, _ = register(laptop)
        attacker_key = ec.generate_private_key(ec.SECP256R1())
        cases = {
            "signed by another key": {"key": attacker_key},
            "wrong origin": {"origin": "https://evil.example"},
            "wrong relying party": {"rp_id": "evil.example"},
            "no user verification": {"flags": 0x01},
        }
        for label, kwargs in cases.items():
            assert passkey_login(client, device, **kwargs).status_code == 401, label
            assert client.get("/auth/me").json() == {"user": None}, label
        assert passkey_login(client, device).status_code == 200  # the genuine one still works


def test_a_cloned_authenticator_is_caught_by_the_signature_counter():
    with TestClient(app) as laptop, TestClient(app) as client:
        sign_up(laptop, "pk-clone@example.com")
        device, _, _ = register(laptop)
        device.counter = 10
        assert passkey_login(client, device).status_code == 200
        device.counter = 3  # a copy that was made earlier and now replays a lower count
        assert passkey_login(client, device, bump=0).status_code == 401


def test_unknown_credentials_and_reused_challenges_are_refused():
    with TestClient(app) as laptop, TestClient(app) as client:
        sign_up(laptop, "pk-unknown@example.com")
        device, _, _ = register(laptop)
        stranger = SoftKey()  # never registered anywhere
        stranger.user_handle = device.user_handle
        assert passkey_login(client, stranger).status_code == 401
        started = client.post("/auth/passkeys/login/options").json()
        payload = {
            "challenge_id": started["challenge_id"],
            "credential": device.get(started["options"]),
        }
        assert client.post("/auth/passkeys/login/verify", json=payload).status_code == 200
        client.post("/auth/logout")
        assert client.post("/auth/passkeys/login/verify", json=payload).status_code == 401  # replay
        assert (
            client.post(
                "/auth/passkeys/login/verify", json={"challenge_id": "nope", "credential": {}}
            ).status_code
            == 401
        )


def test_login_options_reveal_nothing_about_any_account():
    with TestClient(app) as client:
        options = client.post("/auth/passkeys/login/options").json()["options"]
        assert "allowCredentials" not in options or options["allowCredentials"] == []
        assert options["userVerification"] == "required" and options["rpId"] == "localhost"


# --- re-authentication and removal ---


def test_a_passkey_can_confirm_identity_for_sensitive_changes(monkeypatch):
    with TestClient(app) as client:
        sign_up(client, "pk-reauth@example.com")
        device, _, _ = register(client)
        base = store.now()
        monkeypatch.setattr(store, "now", lambda: base + settings.reauth_minutes * 60 + 5)
        assert client.post("/auth/sessions/revoke-others").json()["code"] == "reauth_required"
        started = client.post("/auth/reauth/passkey/options").json()
        proof = {
            "method": "passkey",
            "challenge_id": started["challenge_id"],
            "credential": device.get(started["options"]),
        }
        assert client.post("/auth/reauth", json=proof).status_code == 200
        assert client.post("/auth/sessions/revoke-others").status_code == 200


def test_another_accounts_passkey_cannot_confirm_my_identity():
    with TestClient(app) as me, TestClient(app) as other:
        sign_up(me, "me-pk@example.com")
        sign_up(other, "other-pk@example.com")
        register(me)
        theirs, _, _ = register(other)
        started = me.post("/auth/reauth/passkey/options").json()
        proof = {
            "method": "passkey",
            "challenge_id": started["challenge_id"],
            "credential": theirs.get(started["options"]),
        }
        assert me.post("/auth/reauth", json=proof).status_code == 403


def test_the_last_way_in_cannot_be_removed():
    with TestClient(app) as client:
        request_signup(client, "only-pk@example.com")
        from tests.test_auth import token_from_mail

        client.post("/auth/signup/verify", json={"token": token_from_mail()})
        device, _, _ = register(
            client
        )  # no password, no provider: the passkey is the only credential
        blocked = client.delete(f"/auth/passkeys/{b64(device.credential_id)}")
        assert blocked.status_code == 409
        assert (
            client.post(
                "/auth/password/change", json={"new_password": "a brand new passphrase!"}
            ).status_code
            == 200
        )
        assert client.delete(f"/auth/passkeys/{b64(device.credential_id)}").status_code == 204
        assert client.delete(f"/auth/passkeys/{b64(device.credential_id)}").status_code == 404
        assert any("passkey was removed" in m["text"] for m in mail.outbox)


def test_rename_and_ownership_of_passkeys():
    with TestClient(app) as mine, TestClient(app) as other:
        sign_up(mine, "rename-pk@example.com")
        sign_up(other, "rename-other@example.com")
        device, _, _ = register(mine)
        credential = b64(device.credential_id)
        assert (
            mine.patch(
                f"/auth/passkeys/{credential}", json={"name": "  Work   MacBook "}
            ).status_code
            == 200
        )
        assert mine.get("/auth/security").json()["passkeys"][0]["name"] == "Work MacBook"
        assert (
            other.patch(f"/auth/passkeys/{credential}", json={"name": "mine now"}).status_code
            == 404
        )
        assert other.delete(f"/auth/passkeys/{credential}").status_code == 404


def test_security_checkup_scores_the_account():
    with TestClient(app) as client:
        sign_up(client, "checkup@example.com")
        base = client.get("/auth/security").json()["checkup"]
        assert base["score"] == 40 and {i["id"]: i["done"] for i in base["items"]} == {
            "email": True,
            "signin": True,
            "passkey": False,
            "mfa": False,
        }
        register(client)
        assert client.get("/auth/security").json()["checkup"]["score"] == 100


def test_users_with_a_password_still_sign_in_normally_after_adding_a_passkey():
    with TestClient(app) as client:
        sign_up(client, "both@example.com")
        register(client)
        client.post("/auth/logout")
        assert login(client, "both@example.com", PASSWORD).status_code == 200
