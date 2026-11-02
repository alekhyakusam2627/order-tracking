import hashlib
import hmac
import base64

import httpx

from .config import get_settings
from .schemas import TrackingInfo


async def register_tracking(info: TrackingInfo, user_phone: str) -> tuple[str, str]:
    settings = get_settings()
    if not settings.aftership_api_key:
        return "", "Pending carrier registration"
    payload = {
        "tracking": {
            "tracking_number": info.tracking_number,
            "slug": info.carrier,
            "title": info.item_label or "Online order",
            "smses": [user_phone.removeprefix("whatsapp:")],
        }
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.aftership.com/tracking/2026-07/trackings",
            json=payload,
            headers={"as-api-key": settings.aftership_api_key, "Content-Type": "application/json"},
        )
        response.raise_for_status()
    tracking = response.json().get("data", {}).get("tracking", {})
    return str(tracking.get("id", "")), str(tracking.get("tag", "Pending"))


def valid_aftership_signature(body: bytes, signature: str | None) -> bool:
    secret = get_settings().aftership_webhook_secret
    if not secret:
        return True
    if not signature:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature)


async def send_whatsapp(to: str, message: str) -> None:
    settings = get_settings()
    if not all((settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_number)):
        return
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            data={"From": settings.twilio_whatsapp_number, "To": to, "Body": message},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
        response.raise_for_status()
