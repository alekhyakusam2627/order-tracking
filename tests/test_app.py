import os
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["DATABASE_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = ""
os.environ["TWILIO_POLLING_ENABLED"] = "false"
os.environ["ENABLE_DASHBOARD"] = "false"

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ready"}


def test_security_headers():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


def test_unsigned_webhook_is_rejected_when_twilio_is_configured():
    with TestClient(app) as client:
        response = client.post("/webhooks/whatsapp", data={"From": "whatsapp:+15550001111"})
        assert response.status_code == 403


def test_dashboard_requires_auth_or_is_disabled():
    with TestClient(app) as client:
        assert client.get("/").status_code in (401, 404, 503)
