from app.customer_auth import normalize_whatsapp_phone, phone_from_session, session_token


def test_normalizes_customer_phone():
    assert normalize_whatsapp_phone("+1 (604) 555-0123") == "whatsapp:+16045550123"


def test_rejects_phone_without_country_code_length():
    assert normalize_whatsapp_phone("12345") is None


def test_customer_session_round_trip():
    phone = "whatsapp:+16045550123"
    assert phone_from_session(session_token(phone)) == phone


def test_expired_customer_session_is_rejected():
    assert phone_from_session(session_token("whatsapp:+16045550123", lifetime_seconds=-1)) is None
