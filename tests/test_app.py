import os
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["DATABASE_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = ""
os.environ["TWILIO_POLLING_ENABLED"] = "false"
os.environ["ENABLE_DASHBOARD"] = "false"

from fastapi.testclient import TestClient

from app.main import app
from app.customer_access import customer_token
from app.database import save_shipment


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


def test_customer_dashboard_only_returns_that_customers_shipments():
    first = "whatsapp:+15550001001"
    second = "whatsapp:+15550001002"
    save_shipment(first, "0106716248026353", "canada-post", "First package")
    save_shipment(second, "123456789012", "fedex", "Second package")

    with TestClient(app) as client:
        response = client.get(f"/api/customer/{customer_token(first)}/shipments")
        assert response.status_code == 200
        shipments = response.json()["shipments"]
        assert [item["item_label"] for item in shipments] == ["First package"]
        assert all("user_phone" not in item for item in shipments)


def test_customer_dashboard_rejects_invalid_token():
    with TestClient(app) as client:
        assert client.get("/api/customer/not-a-valid-token/shipments").status_code == 404
