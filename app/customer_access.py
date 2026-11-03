import hashlib
import hmac

from .config import get_settings
from .database import list_customer_phones


def _secret() -> bytes:
    settings = get_settings()
    value = settings.customer_dashboard_secret or settings.twilio_auth_token
    if not value:
        raise RuntimeError("Customer dashboard secret is not configured")
    return value.encode()


def customer_token(phone: str) -> str:
    return hmac.new(_secret(), phone.encode(), hashlib.sha256).hexdigest()


def phone_from_customer_token(token: str) -> str | None:
    if len(token) != 64:
        return None
    return next(
        (phone for phone in list_customer_phones() if hmac.compare_digest(token, customer_token(phone))),
        None,
    )


def customer_dashboard_url(phone: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/customer/{customer_token(phone)}"
