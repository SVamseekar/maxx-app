from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from maxx.main import app, get_connection

client = TestClient(app)


def test_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "maxx-api"}


def test_readiness_with_database():
    class Connection:
        def execute(self, statement):
            assert str(statement) == "SELECT 1"

    app.dependency_overrides[get_connection] = lambda: Connection()
    try:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_readiness_without_database_does_not_leak_credentials():
    def unavailable():
        raise OperationalError("postgresql://secret", {}, Exception("private password"))

    app.dependency_overrides[get_connection] = unavailable
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unavailable",
            "service": "maxx-api",
            "database": "unavailable",
        }
        assert "private" not in response.text
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_the_example_environment_file_loads(monkeypatch):
    from maxx.config import ROOT, Settings

    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    loaded = Settings(_env_file=ROOT / ".env.example")
    assert loaded.demo_tools is None and loaded.docs_enabled is None
    assert loaded.tracking_mode == "simulator" and loaded.verify_mode == "simulator"
