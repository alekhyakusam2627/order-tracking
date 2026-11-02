from app.parser import parse_tracking_text


def test_parses_fedex_text():
    result = parse_tracking_text("FedEx tracking 123456789012")
    assert result is not None
    assert result.carrier == "fedex"
    assert result.tracking_number == "123456789012"


def test_parses_ups_text():
    result = parse_tracking_text("Your parcel shipped: 1Z999AA10123456784")
    assert result is not None
    assert result.carrier == "ups"


def test_rejects_order_number():
    assert parse_tracking_text("Order 12345 is confirmed") is None
