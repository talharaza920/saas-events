"""M1 smoke tests: the API boots and the health probe responds."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "service" in body
    # The probe really pings the DB now (REVIEW_BACKLOG P1-10).
    assert body["db_ok"] is True


def test_openapi_served():
    """The OpenAPI schema must be available — the frontend generates types from it."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"]
