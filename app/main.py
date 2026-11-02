import asyncio
from contextlib import asynccontextmanager, suppress
from html import escape

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from twilio.request_validator import RequestValidator

from .config import get_settings
from .database import attach_aftership, init_db, list_shipments, save_shipment, update_status
from .integrations import register_tracking, send_whatsapp, valid_aftership_signature
from .parser import parse_message
from .poller import poll_twilio_messages


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    poller = None
    if settings.twilio_polling_enabled and settings.twilio_account_sid and settings.twilio_auth_token:
        poller = asyncio.create_task(poll_twilio_messages())
    yield
    if poller:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller


app = FastAPI(title="Forwarding Bot", version="1.0.0", lifespan=lifespan)


def twiml(message: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
    return Response(body, media_type="application/xml")


async def validate_twilio(request: Request, form: dict) -> None:
    settings = get_settings()
    signature = request.headers.get("x-twilio-signature")
    if not settings.twilio_auth_token:
        return
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")
    url = settings.public_base_url.rstrip("/") + request.url.path if settings.public_base_url else str(request.url)
    if not RequestValidator(settings.twilio_auth_token).validate(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    form = dict(await request.form())
    await validate_twilio(request, form)
    user_phone = str(form.get("From", ""))
    text = str(form.get("Body", ""))
    media_url = str(form.get("MediaUrl0", "")) or None
    if not user_phone or (not text and not media_url):
        return twiml("Please forward a shipping message or tracking screenshot.")
    try:
        info = await parse_message(text, media_url)
        if not info.tracking_number:
            return twiml("I couldn't find a reliable tracking number. Please send a clearer screenshot or the shipping message text.")
        carrier = info.carrier or "unknown"
        label = info.item_label or "Online order"
        shipment_id = save_shipment(user_phone, info.tracking_number, carrier, label)
        aftership_id, status = await register_tracking(info, user_phone)
        attach_aftership(shipment_id, aftership_id, status)
        return twiml(f"Got it! I'm tracking {label} with {carrier}: {info.tracking_number}.")
    except Exception:
        return twiml("I couldn't process that shipment right now. Please try again shortly.")


@app.post("/webhooks/aftership")
async def aftership_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    if not valid_aftership_signature(body, request.headers.get("aftership-hmac-sha256")):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    payload = await request.json()
    message = payload.get("msg", {})
    tracking = message.get("tracking", message) or payload.get("data", {}).get("tracking", {})
    number = tracking.get("tracking_number")
    status = tracking.get("tag") or tracking.get("subtag_message")
    if not number or not status:
        return {"accepted": True, "updated": False}
    shipment = update_status(str(number), str(status))
    if shipment:
        background_tasks.add_task(
            send_whatsapp,
            shipment["user_phone"],
            f"Package update: {shipment['item_label']} is now {status}.",
        )
    return {"accepted": True, "updated": bool(shipment)}


@app.get("/api/shipments")
def shipments(phone: str | None = None):
    if not get_settings().enable_dashboard:
        raise HTTPException(status_code=404, detail="Dashboard disabled")
    return {"shipments": list_shipments(phone)}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if not get_settings().enable_dashboard:
        raise HTTPException(status_code=404, detail="Dashboard disabled")
    return HTMLResponse("""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Package Tracker</title><style>body{font:15px system-ui;margin:0;background:#f5f6fa;color:#172033}main{max-width:1050px;margin:48px auto;padding:0 20px}h1{font-size:32px}.card{background:white;border-radius:16px;box-shadow:0 8px 30px #17203312;overflow:hidden}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:15px;border-bottom:1px solid #edf0f5}th{background:#fafbfc;color:#687386}.status{display:inline-block;padding:5px 9px;border-radius:99px;background:#e8f1ff;color:#1262c5}@media(max-width:700px){th:nth-child(4),td:nth-child(4){display:none}}</style></head>
<body><main><h1>Your deliveries</h1><p>Forward a shipping message or screenshot to the WhatsApp bot. New deliveries appear here automatically.</p><div class='card'><table><thead><tr><th>Item</th><th>Carrier</th><th>Tracking</th><th>Customer</th><th>Status</th></tr></thead><tbody id='rows'></tbody></table></div></main>
<script>const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(){const d=await fetch('/api/shipments').then(r=>r.json());document.querySelector('#rows').innerHTML=d.shipments.map(x=>`<tr><td>${e(x.item_label)}</td><td>${e(x.carrier)}</td><td>${e(x.tracking_number)}</td><td>${e(x.user_phone)}</td><td><span class=status>${e(x.status)}</span></td></tr>`).join('')||'<tr><td colspan=5>No deliveries yet.</td></tr>'}load();setInterval(load,15000)</script></body></html>""")
