import base64
import hashlib
import hmac
import json
import re
import secrets
import time

from .config import get_settings


def normalize_whatsapp_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15:
        return None
    return f"whatsapp:+{digits}"


def new_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def code_hash(phone: str, code: str) -> str:
    secret = get_settings().customer_dashboard_secret or get_settings().twilio_auth_token
    if not secret:
        raise RuntimeError("Customer dashboard secret is not configured")
    return hmac.new(secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def session_token(phone: str, lifetime_seconds: int = 30 * 24 * 60 * 60) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"phone": phone, "exp": int(time.time()) + lifetime_seconds}, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = code_hash("session", payload)
    return f"{payload}.{signature}"


def phone_from_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload, supplied = token.split(".", 1)
        if not hmac.compare_digest(supplied, code_hash("session", payload)):
            return None
        padding = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
        phone = str(data["phone"])
        if int(data["exp"]) < int(time.time()) or not phone.startswith("whatsapp:+"):
            return None
        return phone
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
