"""OAuth / OpenID Connect sign-in for Google, Apple, Microsoft and GitHub against a simulated IdP.

The simulator signs real RS256 ID tokens and serves a JWKS, so signature, issuer, audience, expiry
and nonce checks are exercised for real rather than mocked away.
"""

import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx2 as httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi.testclient import TestClient

from maxx.auth import jwtutil, oauth
from maxx.config import settings
from maxx.main import app
from tests.conftest import sign_up

PASSWORD = "correct horse battery"
APPLE_CLIENT = "com.example.maxx.web"
PERSONAL = oauth.MICROSOFT_PERSONAL_TENANT
WORK_TENANT = "11111111-2222-3333-4444-555555555555"


def b64(data: bytes) -> str:
    return jwtutil.b64url_encode(data)


class IdP:
    """Stands in for all four providers' token, key and profile endpoints."""

    def __init__(self):
        self.keys = {"k1": rsa.generate_private_key(65537, 2048)}
        self.apple_key = ec.generate_private_key(ec.SECP256R1())
        self.nonce: dict[str, str] = {}
        self.issued: dict[str, dict] = {}
        self.token_calls: list[httpx.Request] = []
        self.ms_userinfo: dict = {"email": "fallback@example.com"}
        self.github = ({"id": 4242, "login": "octo", "avatar_url": "https://img.example/o.png"}, [])

    # -- tokens ------------------------------------------------------------------------------
    def jwks(self) -> dict:
        keys = []
        for kid, key in self.keys.items():
            numbers = key.public_key().public_numbers()
            keys.append(
                {
                    "kty": "RSA",
                    "kid": kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": b64(numbers.n.to_bytes(256, "big")),
                    "e": b64(numbers.e.to_bytes(3, "big")),
                }
            )
        return {"keys": keys}

    def sign(self, claims: dict, kid="k1", key=None, alg="RS256") -> str:
        head = b64(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
        body = b64(json.dumps(claims).encode())
        if alg == "none":
            return f"{head}.{body}."
        signature = (key or self.keys[kid]).sign(
            f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{head}.{body}.{b64(signature)}"

    def claims(self, provider: str, **override) -> dict:
        now = int(time.time())
        base = {"iat": now, "exp": now + 600, "nonce": self.nonce.get(provider)}
        if provider == "google":
            base |= {
                "iss": "https://accounts.google.com",
                "aud": "gid",
                "sub": "g-1",
                "email": "Gina@Example.com",
                "email_verified": True,
                "name": "Gina G",
                "picture": "https://img.example/g.png",
            }
        elif provider == "apple":
            base |= {
                "iss": "https://appleid.apple.com",
                "aud": APPLE_CLIENT,
                "sub": "a-1",
                "email": "gina@example.com",
                "email_verified": "true",
                "is_private_email": "false",
            }
        else:
            tid = override.get("tid", PERSONAL)
            base |= {
                "iss": f"https://login.microsoftonline.com/{tid}/v2.0",
                "aud": "mid",
                "sub": "m-1",
                "tid": tid,
                "email": "gina@example.com",
                "name": "Gina M",
            }
        return {**base, **override}

    def issue(self, provider: str, **override):
        self.issued[provider] = self.sign(self.claims(provider, **override))

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]

        def tenant(template: str) -> str:
            return template.format(tenant=oauth.microsoft_tenant())

        tokens = {
            settings.google_token_url: "google",
            settings.apple_token_url: "apple",
            tenant(settings.microsoft_token_url): "microsoft",
        }
        jwks = {
            settings.google_jwks_url,
            settings.apple_jwks_url,
            tenant(settings.microsoft_jwks_url),
        }
        if url in tokens:
            self.token_calls.append(request)
            token = self.issued.get(tokens[url])
            if token is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200, json={"access_token": f"{tokens[url]}-access", "id_token": token}
            )
        if url == settings.github_token_url:
            self.token_calls.append(request)
            return httpx.Response(200, json={"access_token": "h-token"})
        if url in jwks:
            return httpx.Response(200, json=self.jwks())
        if url == settings.microsoft_userinfo_url:
            return httpx.Response(200, json=self.ms_userinfo)
        if url == settings.github_user_url:
            return httpx.Response(200, json=self.github[0])
        if url == settings.github_emails_url:
            return httpx.Response(200, json=self.github[1])
        return httpx.Response(404)


@pytest.fixture
def idp(monkeypatch):
    provider = IdP()
    pem = provider.apple_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    for name, value in {
        "google_client_id": "gid",
        "google_client_secret": "gsecret",
        "microsoft_client_id": "mid",
        "microsoft_client_secret": "msecret",
        "github_client_id": "hid",
        "github_client_secret": "hsecret",
        "apple_client_id": APPLE_CLIENT,
        "apple_team_id": "TEAM123456",
        "apple_key_id": "KEY1234567",
        "apple_private_key": pem.replace("\n", "\\n"),
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(oauth, "transport", httpx.MockTransport(provider.handler))
    return provider


def start(client, provider, idp, next_path="/blocs", **params):
    response = client.get(
        f"/auth/oauth/{provider}/start",
        params={"next": next_path, **params},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    if "nonce" in query:
        idp.nonce[provider] = query["nonce"][0]
    return response, query


def finish(client, provider, state, code="the-code", **extra):
    return client.get(
        f"/auth/oauth/{provider}/callback",
        params={"code": code, "state": state, **extra},
        follow_redirects=False,
    )


def sign_in(client, provider, idp, next_path="/blocs", **extra):
    _, query = start(client, provider, idp, next_path)
    return finish(client, provider, query["state"][0], **extra)


def me(client):
    return client.get("/auth/me").json()["user"]


# --- discovery and the authorisation request ---


def test_providers_list_in_display_order_and_report_configuration(monkeypatch):
    with TestClient(app) as client:
        body = client.get("/auth/providers").json()
        assert [p["id"] for p in body["oauth"]] == ["google", "apple", "microsoft", "github"]
        assert not any(p["enabled"] for p in body["oauth"])
        monkeypatch.setattr(settings, "google_client_id", "gid")
        monkeypatch.setattr(settings, "google_client_secret", "gsecret")
        monkeypatch.setattr(settings, "apple_client_id", "only-this-one")  # needs all four fields
        enabled = {p["id"]: p["enabled"] for p in client.get("/auth/providers").json()["oauth"]}
        assert enabled == {"google": True, "apple": False, "microsoft": False, "github": False}


def test_unconfigured_or_unknown_provider_returns_to_login():
    with TestClient(app) as client:
        for provider in ("google", "apple", "myspace"):
            response = client.get(f"/auth/oauth/{provider}/start", follow_redirects=False)
            assert response.headers["location"] == "/login?error=oauth_unavailable"


def test_authorisation_requests_carry_pkce_state_nonce_and_exact_redirects(idp):
    with TestClient(app) as client:
        for provider, host, oidc in (
            ("google", "accounts.google.com", True),
            ("apple", "appleid.apple.com", True),
            ("microsoft", "login.microsoftonline.com", True),
            ("github", "github.com", False),
        ):
            response, query = start(client, provider, idp)
            assert urlsplit(response.headers["location"]).netloc == host
            assert (
                query["code_challenge_method"] == ["S256"] and len(query["code_challenge"][0]) == 43
            )
            assert query["redirect_uri"] == [
                f"http://localhost:3001/api/auth/oauth/{provider}/callback"
            ]
            assert ("nonce" in query) is oidc and len(query["state"][0]) > 30
            assert "httponly" in response.headers["set-cookie"].lower()
        _, apple = start(client, "apple", idp)
        assert apple["response_mode"] == ["form_post"] and apple["scope"] == ["name email"]
        assert apple["client_id"] == [APPLE_CLIENT]
        _, google = start(client, "google", idp)
        assert "response_mode" not in google and google["scope"] == ["openid email profile"]
        _, microsoft = start(client, "microsoft", idp)
        assert microsoft["prompt"] == ["select_account"]


def test_microsoft_uses_the_configured_tenant_in_every_endpoint(idp, monkeypatch):
    monkeypatch.setattr(settings, "microsoft_tenant", "consumers")
    with TestClient(app) as client:
        response, _ = start(client, "microsoft", idp)
        assert "/consumers/oauth2/v2.0/authorize" in response.headers["location"]


# --- Google ---


def test_google_sign_in_verifies_the_id_token_and_creates_an_account(idp):
    with TestClient(app) as client:
        _, query = start(client, "google", idp, "/blocs?x=1")
        idp.issue("google")
        done = finish(client, "google", query["state"][0])
        assert done.status_code == 302 and done.headers["location"] == "/blocs?x=1"
        call = idp.token_calls[-1]
        assert b"code_verifier=" in call.content and b"gsecret" in call.content
        user = me(client)
        assert user["email"] == "gina@example.com" and user["email_verified"] is True
        assert user["display_name"] == "Gina G" and user["providers"] == ["google"]
        assert user["has_password"] is False and user["avatar_url"] == "https://img.example/g.png"
        client.post("/auth/logout")
        _, again = start(client, "google", idp)
        idp.issue("google")
        finish(client, "google", again["state"][0])
        assert me(client)["id"] == user["id"]


@pytest.mark.parametrize(
    "tamper",
    [
        {"nonce": "somebody-elses-nonce"},
        {"aud": "another-app"},
        {"exp": int(time.time()) - 3600},
        {"iss": "https://evil.example"},
        {"sub": ""},
    ],
    ids=["nonce", "audience", "expired", "issuer", "no-subject"],
)
def test_google_rejects_id_tokens_that_fail_validation(idp, tamper):
    with TestClient(app) as client:
        _, query = start(client, "google", idp)
        idp.issue("google", **tamper)
        done = finish(client, "google", query["state"][0])
        assert done.headers["location"] == "/login?error=oauth_failed"
        assert me(client) is None


def test_id_tokens_with_forged_signatures_or_algorithms_are_rejected(idp):
    attacker_key = rsa.generate_private_key(65537, 2048)
    # Built after the nonce is known, so only the signature or algorithm can be at fault.
    cases = {
        "foreign key": lambda c: idp.sign(c, key=attacker_key),
        "alg none": lambda c: idp.sign(c, alg="none"),
        "unknown kid": lambda c: idp.sign(c, kid="zz", key=idp.keys["k1"]),
        "hmac confusion": lambda c: ".".join(
            [b64(b'{"alg":"HS256","kid":"k1"}'), b64(json.dumps(c).encode()), b64(b"x")]
        ),
        "garbage": lambda c: "not-a-jwt",
    }
    with TestClient(app) as client:
        for label, build in cases.items():
            _, query = start(client, "google", idp)
            idp.issued["google"] = build(idp.claims("google"))
            done = finish(client, "google", query["state"][0])
            assert done.headers["location"] == "/login?error=oauth_failed", label
            assert me(client) is None, label
        # Control: the same claims signed properly are accepted.
        _, query = start(client, "google", idp)
        idp.issue("google")
        assert finish(client, "google", query["state"][0]).headers["location"] == "/blocs"


def test_key_rotation_refetches_signing_keys_once(idp):
    with TestClient(app) as client:
        _, first = start(client, "google", idp)
        idp.issue("google")
        finish(client, "google", first["state"][0])  # caches {k1}
        client.post("/auth/logout")
        idp.keys = {"k2": rsa.generate_private_key(65537, 2048)}  # the provider rotates keys
        _, second = start(client, "google", idp)
        idp.issued["google"] = idp.sign(idp.claims("google"), kid="k2")
        assert finish(client, "google", second["state"][0]).headers["location"] == "/blocs"
        assert me(client) is not None


def test_unverified_google_email_never_attaches_to_an_account(idp):
    with TestClient(app) as client:
        sign_up(client, "gina@example.com")
        client.post("/auth/logout")
        _, query = start(client, "google", idp)
        idp.issue("google", email_verified=False)
        done = finish(client, "google", query["state"][0])
        assert done.headers["location"] == "/login?error=oauth_no_email"
        assert me(client) is None


# --- account takeover defences ---


def test_verified_account_keeps_its_password_when_a_provider_is_linked(idp):
    with TestClient(app) as client:
        existing = sign_up(client, "gina@example.com")  # confirmed by emailed link, password set
        client.post("/auth/logout")
        _, query = start(client, "google", idp)
        idp.issue("google")
        assert finish(client, "google", query["state"][0]).status_code == 302
        user = me(client)
        assert user["id"] == existing["id"] and user["providers"] == ["google"]
        assert user["has_password"] is True
        client.post("/auth/logout")
        done = client.post("/auth/login", json={"email": "gina@example.com", "password": PASSWORD})
        assert done.status_code == 200


def test_a_pending_signup_for_someone_elses_address_gives_the_attacker_nothing(idp):
    """The attacker requests sign-up for the victim's address; the victim then uses Google."""
    with TestClient(app) as attacker, TestClient(app) as victim:
        assert attacker.post("/auth/signup", json={"email": "gina@example.com"}).status_code == 202
        _, query = start(victim, "google", idp)
        idp.issue("google")
        finish(victim, "google", query["state"][0])
        owner = me(victim)
        assert owner["email"] == "gina@example.com" and owner["email_verified"] is True
        assert owner["providers"] == ["google"] and owner["has_password"] is False
        assert attacker.get("/auth/me").json() == {"user": None}


def test_a_legacy_unverified_password_account_is_stripped_when_the_real_owner_signs_in(idp):
    """Accounts from before verify-first sign-up may hold an unproven password and live sessions."""
    from maxx.auth import store
    from maxx.auth.security import hash_password

    planted = store.create_user("gina@example.com", "Planted", hash_password("attacker secret!"))
    token = store.create_session(planted.id, "attacker", 30)
    with TestClient(app) as victim, TestClient(app) as attacker:
        attacker.cookies.set("maxx_session", token)
        _, query = start(victim, "google", idp)
        idp.issue("google")
        finish(victim, "google", query["state"][0])
        owner = me(victim)
        assert owner["id"] == planted.id and owner["has_password"] is False
        assert attacker.get("/auth/me").json() == {"user": None}
        denied = TestClient(app).post(
            "/auth/login", json={"email": "gina@example.com", "password": "attacker secret!"}
        )
        assert denied.status_code == 401


def test_state_must_come_from_the_browser_that_started_the_flow_and_is_single_use(idp):
    with TestClient(app) as victim, TestClient(app) as attacker:
        _, query = start(attacker, "google", idp)
        idp.issue("google")
        refused = finish(victim, "google", query["state"][0])
        assert refused.headers["location"] == "/login?error=oauth_state"
        assert me(victim) is None
        assert finish(attacker, "google", query["state"][0]).status_code == 302
        replay = finish(attacker, "google", query["state"][0])
        assert replay.headers["location"] == "/login?error=oauth_state"


def test_a_state_for_one_provider_is_useless_at_another_providers_callback(idp):
    """Mix-up defence: each provider has its own redirect URI and the state is bound to it."""
    with TestClient(app) as client:
        _, query = start(client, "google", idp)
        idp.issue("google")
        mixed = finish(client, "github", query["state"][0])
        assert mixed.headers["location"] == "/login?error=oauth_state"
        assert me(client) is None


def test_denied_and_failing_providers_are_reported_safely(idp, monkeypatch):
    with TestClient(app) as client:
        denied = client.get(
            "/auth/oauth/google/callback", params={"error": "access_denied"}, follow_redirects=False
        )
        assert denied.headers["location"] == "/login?error=oauth_denied"
        _, query = start(client, "google", idp)
        idp.issued.pop("google", None)  # the token endpoint answers 400
        failed = finish(client, "google", query["state"][0])
        assert failed.headers["location"] == "/login?error=oauth_failed"
        assert me(client) is None


# --- Microsoft ---


def test_microsoft_personal_account_is_trusted_for_its_email(idp):
    with TestClient(app) as client:
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft")
        finish(client, "microsoft", query["state"][0])
        user = me(client)
        assert user["email"] == "gina@example.com" and user["email_verified"] is True
        assert user["providers"] == ["microsoft"] and user["display_name"] == "Gina M"


def test_microsoft_work_account_email_is_untrusted_without_a_verified_domain(idp):
    """nOAuth: an Entra admin can set any email on an account. Never link on it."""
    with TestClient(app) as client:
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft", tid=WORK_TENANT)
        done = finish(client, "microsoft", query["state"][0])
        assert done.headers["location"] == "/login?error=oauth_no_email"
        assert me(client) is None
        # With Microsoft's xms_edov claim set to true the domain is verified.
        _, again = start(client, "microsoft", idp)
        idp.issue("microsoft", tid=WORK_TENANT, xms_edov=True)
        assert finish(client, "microsoft", again["state"][0]).headers["location"] == "/blocs"
        assert me(client)["email_verified"] is True


def test_microsoft_xms_edov_must_be_a_real_boolean(idp):
    with TestClient(app) as client:
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft", tid=WORK_TENANT, xms_edov="true")
        assert (
            finish(client, "microsoft", query["state"][0]).headers["location"]
            == "/login?error=oauth_no_email"
        )


def test_microsoft_falls_back_to_userinfo_when_the_token_has_no_email(idp):
    with TestClient(app) as client:
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft", email=None)
        finish(client, "microsoft", query["state"][0])
        assert me(client)["email"] == "fallback@example.com"


def test_microsoft_issuer_must_match_the_tenant_in_the_token(idp):
    with TestClient(app) as client:
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft", iss="https://login.microsoftonline.com/someone-else/v2.0")
        assert (
            finish(client, "microsoft", query["state"][0]).headers["location"]
            == "/login?error=oauth_failed"
        )


def test_microsoft_tenant_restrictions_are_enforced(idp, monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(settings, "microsoft_tenant", "consumers")
        _, query = start(client, "microsoft", idp)
        idp.issue("microsoft", tid=WORK_TENANT, xms_edov=True)
        assert (
            finish(client, "microsoft", query["state"][0]).headers["location"]
            == "/login?error=oauth_failed"
        )
        monkeypatch.setattr(settings, "microsoft_tenant", WORK_TENANT)
        _, other = start(client, "microsoft", idp)
        idp.issue("microsoft", tid="99999999-0000-0000-0000-000000000000", xms_edov=True)
        assert (
            finish(client, "microsoft", other["state"][0]).headers["location"]
            == "/login?error=oauth_failed"
        )


# --- Apple ---


def apple_post(client, **form):
    """What Apple's browser POST looks like: cross-site, no cookies, form encoded."""
    client.cookies.clear()
    return client.post(
        "/auth/oauth/apple/callback", data=form, headers={"origin": "https://appleid.apple.com"}
    )


def test_apple_form_post_is_relayed_to_the_get_callback_where_every_check_runs(idp):
    with TestClient(app) as client:
        _, query = start(client, "apple", idp)
        state, cookie = query["state"][0], client.cookies.get("maxx_oauth_state")
        relay = apple_post(
            client,
            code="the-code",
            state=state,
            id_token="ignored",
            user=json.dumps({"name": {"firstName": "Gina", "lastName": "Apple"}, "email": "x@y.z"}),
        )
        assert relay.status_code == 200 and "no-store" in relay.headers["cache-control"]
        target = re.search(r'location\.replace\("([^"]+)"\)', relay.text).group(1)
        assert target.startswith("/api/auth/oauth/apple/callback?") and "id_token" not in target
        # The browser then GETs the target from this origin, with the state cookie it kept.
        client.cookies.set("maxx_oauth_state", cookie)
        idp.issue("apple")
        query_string = parse_qs(urlsplit(target).query)
        done = client.get(
            "/auth/oauth/apple/callback",
            params={k: v[0] for k, v in query_string.items()},
            follow_redirects=False,
        )
        assert done.headers["location"] == "/blocs"
        user = me(client)
        assert user["email"] == "gina@example.com" and user["email_verified"] is True
        assert user["display_name"] == "Gina Apple" and user["providers"] == ["apple"]


def test_apple_client_secret_is_a_correct_es256_jwt(idp):
    with TestClient(app) as client:
        _, query = start(client, "apple", idp)
        idp.issue("apple")
        finish(client, "apple", query["state"][0])
        form = parse_qs(idp.token_calls[-1].content.decode())
        secret = form["client_secret"][0]
        header, claims, signing_input, signature = jwtutil.split(secret)
        assert header["alg"] == "ES256" and header["kid"] == "KEY1234567"
        assert claims["iss"] == "TEAM123456" and claims["sub"] == APPLE_CLIENT
        assert claims["aud"] == "https://appleid.apple.com"
        assert 0 < claims["exp"] - claims["iat"] <= 15777000
        r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        idp.apple_key.public_key().verify(
            encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256())
        )
        assert form["client_id"] == [APPLE_CLIENT] and "code_verifier" in form


def test_apple_private_relay_email_and_string_booleans(idp):
    with TestClient(app) as client:
        _, query = start(client, "apple", idp)
        idp.issue("apple", email="abc123@privaterelay.appleid.com", is_private_email="true")
        finish(client, "apple", query["state"][0])
        assert me(client)["email"] == "abc123@privaterelay.appleid.com"
        client.post("/auth/logout")
        _, again = start(client, "apple", idp)
        idp.issue("apple", sub="a-2", email="other@example.com", email_verified="false")
        assert (
            finish(client, "apple", again["state"][0]).headers["location"]
            == "/login?error=oauth_no_email"
        )


def test_apple_relay_page_cannot_be_used_to_inject_script():
    hostile = '"</script><script>alert(1)</script>'
    with TestClient(app) as client:
        response = client.post(
            "/auth/oauth/apple/callback", data={"code": hostile, "state": hostile, "x": "dropped"}
        )
        assert response.text.count("<script") == 1  # only the relay's own script
        nonce = re.search(r'<script nonce="([^"]+)"', response.text).group(1)
        assert f"script-src 'nonce-{nonce}'" in response.headers["content-security-policy"]
        assert "alert(1)" not in response.text and "dropped" not in response.text
        assert "%3C%2Fscript%3E" in response.text


def test_other_forms_still_enforce_the_same_origin_rule():
    with TestClient(app) as client:
        evil = client.post(
            "/auth/login",
            json={"email": "a@b.co", "password": "x"},
            headers={"origin": "https://appleid.apple.com"},
        )
        assert evil.status_code == 403


# --- GitHub, linking and unlinking ---


def test_github_uses_the_verified_primary_email(idp):
    idp.github = (
        {"id": 4242, "login": "octo", "name": None, "avatar_url": "https://img.example/o.png"},
        [
            {"email": "spam@example.com", "primary": False, "verified": False},
            {"email": "Octo@Example.com", "primary": True, "verified": True},
        ],
    )
    with TestClient(app) as client:
        _, query = start(client, "github", idp)
        assert query["scope"] == ["read:user user:email"]
        finish(client, "github", query["state"][0])
        user = me(client)
        assert user["email"] == "octo@example.com" and user["display_name"] == "octo"
        assert user["providers"] == ["github"]


def test_github_without_a_verified_email_cannot_sign_in(idp):
    idp.github = (
        {"id": 7, "login": "ghost"},
        [{"email": "x@example.com", "primary": True, "verified": False}],
    )
    with TestClient(app) as client:
        done = sign_in(client, "github", idp)
        assert done.headers["location"] == "/login?error=oauth_no_email"


def test_one_account_can_link_several_providers_and_unlink_down_to_one(idp):
    with TestClient(app) as client, TestClient(app) as other:
        anonymous = client.get(
            "/auth/oauth/google/start", params={"link": "true"}, follow_redirects=False
        )
        assert anonymous.headers["location"] == "/login?error=signin_required"
        sign_up(client, "linker@example.com")
        for provider in ("google", "microsoft"):
            _, query = start(client, provider, idp, "/account", link="true")
            idp.issue(provider, email="different@example.com")
            done = finish(client, provider, query["state"][0])
            assert done.headers["location"] == f"/account?linked={provider}"
        assert me(client)["providers"] == ["google", "microsoft"]
        assert (
            me(client)["email"] == "linker@example.com"
        )  # linking never changes the account email

        sign_up(other, "thief@example.com")
        _, taken = start(other, "google", idp, "/account", link="true")
        idp.issue("google")
        assert (
            finish(other, "google", taken["state"][0]).headers["location"]
            == "/account?error=oauth_taken"
        )

        assert client.delete("/auth/oauth/google").status_code == 204
        assert client.delete("/auth/oauth/google").status_code == 404
        assert me(client)["providers"] == ["microsoft"]


def test_the_only_way_to_sign_in_cannot_be_unlinked(idp):
    with TestClient(app) as client:
        _, query = start(client, "google", idp)
        idp.issue("google")
        finish(client, "google", query["state"][0])
        blocked = client.delete("/auth/oauth/google")
        assert blocked.status_code == 409 and "password" in blocked.json()["detail"].lower()
        assert (
            client.post(
                "/auth/password/change", json={"new_password": "my first password!"}
            ).status_code
            == 200
        )
        assert client.delete("/auth/oauth/google").status_code == 204


# --- two-step and passkeys are not sidestepped by a provider ---


def link_google(client, idp):
    _, query = start(client, "google", idp, "/account", link="true")
    idp.issue("google")
    return finish(client, "google", query["state"][0])


def test_provider_sign_in_still_asks_for_the_second_step(idp):
    from tests.test_mfa import enrol, later_code

    with TestClient(app) as laptop, TestClient(app) as client:
        user, seed, _ = enrol(laptop, "gina@example.com")
        assert link_google(laptop, idp).headers["location"] == "/account?linked=google"
        _, query = start(client, "google", idp, "/blocs")
        idp.issue("google")
        redirect = finish(client, "google", query["state"][0]).headers["location"]
        assert redirect.startswith("/login?mfa=") and "next=%2Fblocs" in redirect
        assert me(client) is None  # the provider alone did not sign anyone in
        token = parse_qs(urlsplit(redirect).query)["mfa"][0]
        wrong = client.post("/auth/login/mfa", json={"mfa_token": token, "code": "000000"})
        assert wrong.status_code == 401
        done = client.post("/auth/login/mfa", json={"mfa_token": token, "code": later_code(seed)})
        assert done.status_code == 200 and done.json()["user"]["id"] == user["id"]
        assert me(client)["id"] == user["id"]
        reuse = client.post(
            "/auth/login/mfa", json={"mfa_token": token, "code": later_code(seed, 2)}
        )
        assert reuse.status_code == 401  # the pending sign-in is single use


def test_a_trusted_browser_skips_the_second_step_for_provider_sign_in_too(idp):
    from tests.test_mfa import enrol, later_code

    with TestClient(app) as laptop, TestClient(app) as home:
        _, seed, _ = enrol(laptop, "gina@example.com")
        link_google(laptop, idp)
        token = home.post(
            "/auth/login", json={"email": "gina@example.com", "password": PASSWORD}
        ).json()["mfa_token"]
        home.post(
            "/auth/login/mfa",
            json={"mfa_token": token, "code": later_code(seed), "remember": True},
        )
        home.post("/auth/logout")
        _, query = start(home, "google", idp)
        idp.issue("google")
        assert finish(home, "google", query["state"][0]).headers["location"] == "/blocs"
        assert me(home) is not None


def test_a_provider_cannot_attach_itself_by_email_to_a_protected_account(idp):
    from tests.test_mfa import enrol

    with TestClient(app) as laptop, TestClient(app) as stranger:
        enrol(laptop, "gina@example.com")  # two-step verification is on
        _, query = start(stranger, "google", idp)
        idp.issue("google")
        done = finish(stranger, "google", query["state"][0])
        assert done.headers["location"] == "/login?error=oauth_link_required"
        assert me(stranger) is None
        assert me(laptop)["providers"] == []  # nothing was attached


def test_the_same_applies_to_accounts_protected_by_a_passkey(idp):
    from tests.test_passkeys import register

    with TestClient(app) as laptop, TestClient(app) as stranger:
        sign_up(laptop, "gina@example.com")
        register(laptop)
        _, query = start(stranger, "google", idp)
        idp.issue("google")
        done = finish(stranger, "google", query["state"][0])
        assert done.headers["location"] == "/login?error=oauth_link_required"
        assert me(laptop)["providers"] == []


def test_linking_from_settings_is_still_the_supported_route_for_protected_accounts(idp):
    from tests.test_mfa import enrol

    with TestClient(app) as laptop:
        enrol(laptop, "gina@example.com")
        assert link_google(laptop, idp).headers["location"] == "/account?linked=google"
        assert me(laptop)["providers"] == ["google"]
