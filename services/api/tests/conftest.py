"""Audit categories. Integration uses local stores/mock transports, not live APIs."""

import pytest

UNIT_SCAN = {
    "test_score_decimal_shipping_and_excluded_rows",
    "test_null_fields_and_non_positive_prices",
    "test_image_validation",
    "test_grounding_rejects_invented_prices_stock_and_shipping",
    "test_non_usd_comparable_excluded",
    "test_verification_probe_does_not_pass_without_key",
}


def pytest_collection_modifyitems(items):
    for item in items:
        filename = item.path.name
        unit = (
            filename
            in {
                "test_auction.py",
                "test_matching.py",
                "test_evaluation.py",
                "test_core_completion.py",
            }
            and item.name != "test_configured_cost_is_logged_from_transport_usage"
            or item.name == "test_private_seller_contexts_isolate_other_sellers"
            or filename == "test_scan.py"
            and item.name in UNIT_SCAN
            or item.name
            in {
                "test_state_machine_join_leave_and_commitment_conservation",
                "test_floor_capacity_clamp_and_private_context",
            }
        )
        item.add_marker(pytest.mark.unit if unit else pytest.mark.integration)


# A few real OFAC SDN rows (public domain, US Treasury) and an alias, in the published CSV shape.
SANCTIONS_SDN = (
    '306,"BANCO NACIONAL DE CUBA",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    '36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    '7140,"KARMOOSH, Muwafaq Mustafa Mohammed Ali","individual","IRAQ2",-0- ,-0- ,-0- ,-0- '
    ",-0- ,-0- ,-0- ,-0- \n"
)
SANCTIONS_ALT = '306,220,"aka","NATIONAL BANK OF CUBA",-0- \n'


@pytest.fixture(autouse=True)
def isolate_application_store(tmp_path, monkeypatch):
    from maxx import storage
    from maxx.config import settings
    from maxx.negotiate.store import BlocStore

    store = BlocStore(f"sqlite:///{tmp_path}/application.sqlite")
    monkeypatch.setattr(storage, "get_store", lambda: store)
    monkeypatch.setattr(settings, "worker_enabled", False)
    # Real rates, so every mocked call passes through the budget like a live one.
    monkeypatch.setattr(
        settings, "model_rates_json", type(settings).model_fields["model_rates_json"].default
    )
    # Whatever .env says (a judging window may run live with larger budgets), tests start from the
    # replay modes and the built-in AI limits, and opt in to anything else explicitly.
    for name in ("scan_mode", "match_mode", "negotiation_mode"):
        monkeypatch.setattr(settings, name, "fixture")
    monkeypatch.setattr(settings, "negotiation_replay_fallback", False)
    monkeypatch.setattr(settings, "judge_access_code", "")
    for name, field in type(settings).model_fields.items():
        if name.startswith("ai_"):
            monkeypatch.setattr(settings, name, field.default)
    # Whatever .env says, tests start with the money layer off and opt in explicitly.
    monkeypatch.setattr(settings, "paypal_mode", "off")
    monkeypatch.setattr(settings, "list_cache_seconds", 0)
    monkeypatch.setattr(settings, "seller_review", "auto")
    monkeypatch.setattr(settings, "pyusd_rpc_url", "")
    monkeypatch.setattr(settings, "pyusd_contract", "")
    monkeypatch.setattr(settings, "pyusd_deposit_address", "")
    # Carrier tracking, identity checks and the demo tour are opted into by the tests that need
    # them; by default a seller is live once their payout email is confirmed.
    monkeypatch.setattr(settings, "tracking_mode", "off")
    monkeypatch.setattr(settings, "verify_mode", "off")
    monkeypatch.setattr(settings, "seller_identity_required", False)
    monkeypatch.setattr(settings, "demo_tools", False)
    monkeypatch.setattr(settings, "email_mode", "log")
    from maxx.compliance import sanctions

    sanctions.load(SANCTIONS_SDN, SANCTIONS_ALT, "test")
    sanctions._index.loaded_at = None
    # Accounts: each test starts with an empty limiter and mailbox and cheap password hashing.
    from maxx.auth import mail, oauth, ratelimit, security

    ratelimit.reset()
    oauth.reset_caches()
    monkeypatch.setattr(settings, "hibp_enabled", False)
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret", "")
    mail.outbox.clear()
    monkeypatch.setattr(oauth, "transport", None)
    monkeypatch.setattr(security, "SCRYPT_N", 2**10)
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:3001")
    yield store
    store.engine.dispose()


def sign_up(client, email="buyer@example.com", name="Buyer", password="correct horse battery"):
    """Create an account through the public API the way a person does: request the emailed link,
    follow it (which signs in), then choose a password. The session cookie lands in the jar."""
    import re

    from maxx.auth import mail

    response = client.post("/auth/signup", json={"email": email, "display_name": name})
    assert response.status_code == 202, response.text
    sent = [m for m in mail.outbox if m["to"] == email and "complete-signup" in m["text"]]
    assert sent, "no sign-up email was sent"
    token = re.search(r"token=([\w-]+)", sent[-1]["text"]).group(1)
    verified = client.post("/auth/signup/verify", json={"token": token})
    assert verified.status_code == 200, verified.text
    if password:
        chosen = client.post("/auth/password/change", json={"new_password": password})
        assert chosen.status_code == 200, chosen.text
    return client.get("/auth/me").json()["user"]


@pytest.fixture(autouse=True)
def test_payer():
    """Unit tests call providers directly through mock transports; give them a payer as every
    request entry point does. Routes open their own scopes, in the server's thread."""
    from maxx import budget

    with budget.payer_scope(budget.Payer("system", "test"), 1000):
        yield


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Tests never reach a real provider: any request not on a mock transport fails loudly."""
    import httpx2 as httpx

    def refuse(self, request):
        raise AssertionError(f"Test tried a real network call to {request.url.host}")

    async def refuse_async(self, request):
        refuse(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
