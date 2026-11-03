from app.tracking_urls import carrier_tracking_url


def test_fedex_tracking_url():
    assert carrier_tracking_url("FedEx", "123456789012") == (
        "https://www.fedex.com/fedextrack/?trknbr=123456789012"
    )


def test_tracking_url_encodes_untrusted_number():
    assert carrier_tracking_url("ups", "1Z 123") == "https://www.ups.com/track?tracknum=1Z%20123"


def test_unknown_carrier_has_no_external_link():
    assert carrier_tracking_url("unknown", "123") is None
