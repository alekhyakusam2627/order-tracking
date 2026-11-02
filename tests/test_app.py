import os
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["DATABASE_PATH"] = tempfile.mktemp(suffix=".db")

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_unsigned_webhook_is_rejected_when_twilio_is_configured():
    with TestClient(app) as client:
        response = client.post("/webhooks/whatsapp", data={"From": "whatsapp:+15550001111"})
        assert response.status_code == 403
