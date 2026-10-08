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


@pytest.fixture(autouse=True)
def isolate_application_store(tmp_path, monkeypatch):
    from maxx import storage
    from maxx.config import settings
    from maxx.negotiate.store import BlocStore

    store = BlocStore(f"sqlite:///{tmp_path}/application.sqlite")
    monkeypatch.setattr(storage, "get_store", lambda: store)
    monkeypatch.setattr(settings, "worker_enabled", False)
    monkeypatch.setattr(settings, "model_rates_json", "{}")
    yield store
    store.engine.dispose()
