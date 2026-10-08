from fastapi.testclient import TestClient

from maxx import providers
from maxx.main import app


def test_transparency_only_exposes_metadata(tmp_path, monkeypatch):
    providers.log_call(
        {
            "provider": "nebius",
            "purpose": "seller",
            "model": "test",
            "tokens": {"total_tokens": 9, "private": "SECRET_FLOOR"},
            "latency_ms": 5,
            "status": "ok",
            "cost_usd": None,
            "prompt": "SECRET_FLOOR",
            "api_key": "SECRET_KEY",
        }
    )
    with TestClient(app) as client:
        response = client.get("/transparency")
        assert response.status_code == 200
        data = response.json()
        assert data["calls"][0]["tokens"]["total_tokens"] == 9
        assert "SECRET" not in response.text
        assert "configured_models" in data
        assert data["cost_status"] == "unmeasured"
