import asyncio
import logging

import httpx

from .config import get_settings
from .database import attach_aftership, mark_message_processed, message_processed, save_shipment
from .integrations import register_tracking, send_whatsapp
from .parser import parse_message


logger = logging.getLogger(__name__)


async def _media_url(client: httpx.AsyncClient, account_sid: str, message_sid: str) -> str | None:
    response = await client.get(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}/Media.json"
    )
    response.raise_for_status()
    media = response.json().get("media_list", [])
    if not media:
        return None
    uri = str(media[0].get("uri", "")).removesuffix(".json")
    return f"https://api.twilio.com{uri}" if uri else None


async def process_twilio_message(message: dict, client: httpx.AsyncClient) -> None:
    sid = str(message.get("sid", ""))
    if not sid or message_processed(sid):
        return

    body = str(message.get("body", ""))
    sender = str(message.get("from", ""))
    if body.lower().startswith("join ") or not sender:
        mark_message_processed(sid)
        return

    try:
        media_url = None
        if str(message.get("num_media", "0")) != "0":
            media_url = await _media_url(client, get_settings().twilio_account_sid, sid)
        info = await parse_message(body, media_url)
        if not info.tracking_number:
            mark_message_processed(sid)
            await send_whatsapp(
                sender,
                "I couldn't find a reliable tracking number. Please forward the shipping message or a clearer screenshot.",
            )
        else:
            carrier = info.carrier or "unknown"
            label = info.item_label or "Online order"
            shipment_id = save_shipment(sender, info.tracking_number, carrier, label)
            aftership_id, status = await register_tracking(info, sender)
            attach_aftership(shipment_id, aftership_id, status)
            mark_message_processed(sid)
            await send_whatsapp(
                sender, f"Got it! I'm tracking {label} with {carrier}: {info.tracking_number}."
            )
    except Exception:
        logger.exception("Failed to process Twilio message %s", sid)


async def poll_twilio_messages() -> None:
    settings = get_settings()
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    while True:
        try:
            async with httpx.AsyncClient(auth=auth, timeout=30) as client:
                response = await client.get(url, params={"PageSize": 20})
                response.raise_for_status()
                messages = response.json().get("messages", [])
                for message in reversed(messages):
                    if message.get("direction") == "inbound":
                        await process_twilio_message(message, client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Twilio polling failed")
        await asyncio.sleep(settings.twilio_poll_interval_seconds)
