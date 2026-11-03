import base64
import re

import httpx
from openai import AsyncOpenAI

from .config import get_settings
from .schemas import TrackingInfo


SYSTEM_PROMPT = """You extract package tracking details from forwarded shopping messages and screenshots.
Return a carrier, tracking number, and short item label. Never treat an order number, phone number,
price, or date as a tracking number. Preserve tracking-number letters and digits, removing spaces and
decorative punctuation. If no credible tracking number exists, set tracking_number to null. Use a
lowercase carrier slug when confident (for example usps, ups, fedex, dhl, canada-post,
india-post, bluedart)."""


def parse_tracking_text(text: str) -> TrackingInfo | None:
    compact = text.upper()
    patterns = (
        ("ups", r"\b1Z[0-9A-Z]{16}\b"),
        ("canada-post", r"\b(?:\d{16}|[A-Z]{2}\d{9}CA)\b"),
        ("fedex", r"\b(?:\d{12}|\d{15}|\d{20}|\d{22})\b"),
        ("usps", r"\b(?:9[2345]\d{18,20}|[A-Z]{2}\d{9}US)\b"),
        ("dhl", r"\b(?:\d{10}|\d{16}|[A-Z]{3}\d{7})\b"),
        ("india-post", r"\b[A-Z]{2}\d{9}IN\b"),
    )
    lowered = text.lower()
    hints = {
        "canada-post": ("canada post", "canadapost"),
        "india-post": ("india post", "indiapost"),
        "fedex": ("fedex",),
        "ups": ("ups",),
        "usps": ("usps",),
        "dhl": ("dhl",),
        "bluedart": ("bluedart", "blue dart"),
    }
    carrier_hint = next(
        (carrier for carrier, names in hints.items() if any(name in lowered for name in names)),
        None,
    )
    ordered = sorted(patterns, key=lambda item: item[0] != carrier_hint)
    for carrier, pattern in ordered:
        match = re.search(pattern, compact)
        if match:
            return TrackingInfo(
                carrier=carrier,
                tracking_number=match.group(0),
                item_label=f"{carrier.upper()} package",
            )
    return None


async def _image_data_url(url: str) -> str:
    settings = get_settings()
    auth = None
    if settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
    if len(response.content) > get_settings().max_request_bytes:
        raise ValueError("Image is too large")
    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
    if not content_type.startswith("image/"):
        raise ValueError("Unsupported media type")
    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def parse_message(text: str, media_url: str | None) -> TrackingInfo:
    if not media_url and (parsed := parse_tracking_text(text)):
        return parsed
    content: list[dict] = [{"type": "input_text", "text": text or "No accompanying text."}]
    if media_url:
        content.append({"type": "input_image", "image_url": await _image_data_url(media_url)})

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.parse(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        text_format=TrackingInfo,
    )
    return response.output_parsed or TrackingInfo()
