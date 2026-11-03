from app.customer_access import customer_token, phone_from_customer_token
from app.database import save_shipment


def test_customer_token_round_trip():
    phone = "whatsapp:+15550001111"
    save_shipment(phone, "123456789012", "fedex", "Token test")
    assert phone_from_customer_token(customer_token(phone)) == phone


def test_customer_token_rejects_tampering():
    token = customer_token("whatsapp:+15550001111")
    assert phone_from_customer_token(token + "x") is None
