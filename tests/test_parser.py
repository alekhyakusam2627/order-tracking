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


def test_parses_canada_post_16_digit_number():
    result = parse_tracking_text("Canada Post tracking 0106716248026353")
    assert result is not None
    assert result.carrier == "canada-post"
    assert result.tracking_number == "0106716248026353"


def test_parses_bare_16_digit_number_as_canada_post():
    result = parse_tracking_text("0106716248026353")
    assert result is not None
    assert result.carrier == "canada-post"


def test_dhl_hint_wins_for_16_digit_ecommerce_number():
    result = parse_tracking_text("DHL eCommerce tracking 7123456789123456")
    assert result is not None
    assert result.carrier == "dhl"


def test_parses_india_post_number():
    result = parse_tracking_text("India Post consignment EM123456789IN")
    assert result is not None
    assert result.carrier == "india-post"
    assert result.tracking_number == "EM123456789IN"
