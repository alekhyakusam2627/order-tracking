import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from html import escape

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from twilio.request_validator import RequestValidator

from .config import get_settings
from .customer_auth import code_hash, new_login_code, normalize_whatsapp_phone, phone_from_session, session_token
from .customer_access import phone_from_customer_token
from .customer_pages import APP_PAGE, LOGIN_PAGE
from .database import attach_aftership, consume_login_code, database_ready, init_db, list_shipments, save_login_code, save_shipment, update_status
from .integrations import register_tracking, send_whatsapp, valid_aftership_signature
from .parser import parse_message
from .poller import poll_twilio_messages
from .tracking_urls import carrier_tracking_url


settings = get_settings()
SESSION_COOKIE = "customer_session"
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
security = HTTPBasic(auto_error=False)
REQUESTS = Counter("forwarding_bot_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("forwarding_bot_http_request_seconds", "HTTP request latency", ["method", "path"])


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


app = FastAPI(
    title="Forwarding Bot",
    version="2.0.0",
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_metrics(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_request_bytes:
        return Response("Request too large", status_code=413)
    started = time.perf_counter()
    response = await call_next(request)
    path = request.scope.get("route").path if request.scope.get("route") else "unmatched"
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def require_dashboard_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if not settings.enable_dashboard:
        raise HTTPException(status_code=404, detail="Dashboard disabled")
    if not settings.dashboard_password and not settings.production:
        return
    if not settings.dashboard_password:
        raise HTTPException(status_code=503, detail="Dashboard credentials are not configured")
    valid = bool(credentials) and secrets.compare_digest(credentials.username, settings.dashboard_username)
    valid = valid and secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


def twiml(message: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
    return Response(body, media_type="application/xml")


class PhoneRequest(BaseModel):
    phone: str


class CodeRequest(PhoneRequest):
    code: str


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


@app.get("/ready")
def ready():
    if not database_ready():
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ready"}


@app.get("/metrics")
def metrics(request: Request):
    if settings.metrics_token:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not secrets.compare_digest(supplied, settings.metrics_token):
            raise HTTPException(status_code=401, detail="Authentication required")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
        app_url = f"{settings.public_base_url.rstrip('/')}/app"
        return twiml(
            f"Got it! I'm tracking {label} with {carrier}: {info.tracking_number}. "
            f"Open Package Tracker: {app_url}"
        )
    except Exception:
        logger.exception("Failed to process WhatsApp webhook")
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


@app.get("/api/shipments", dependencies=[Depends(require_dashboard_auth)])
def shipments(phone: str | None = None):
    rows = list_shipments(phone)
    for row in rows:
        row["tracking_url"] = carrier_tracking_url(row["carrier"], row["tracking_number"])
    return {"shipments": rows}


@app.get("/api/customer/{token}/shipments")
def customer_shipments(token: str):
    phone = phone_from_customer_token(token)
    if not phone:
        raise HTTPException(status_code=404, detail="Customer dashboard not found")
    rows = list_shipments(phone)
    for row in rows:
        row.pop("user_phone", None)
        row["tracking_url"] = carrier_tracking_url(row["carrier"], row["tracking_number"])
    return {"shipments": rows}


@app.post("/api/auth/request-code")
async def request_login_code(payload: PhoneRequest):
    phone = normalize_whatsapp_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid number with country code")
    code = new_login_code()
    if not save_login_code(phone, code_hash(phone, code)):
        raise HTTPException(status_code=429, detail="Please wait one minute before requesting another code")
    try:
        await send_whatsapp(phone, f"Your Package Tracker login code is {code}. It expires in 10 minutes.")
    except Exception:
        logger.exception("Failed to send customer login code")
        raise HTTPException(status_code=502, detail="Could not send the WhatsApp code")
    return {"sent": True}


@app.post("/api/auth/verify-code")
def verify_login_code(payload: CodeRequest):
    phone = normalize_whatsapp_phone(payload.phone)
    if not phone or not payload.code.isdigit() or len(payload.code) != 6:
        raise HTTPException(status_code=400, detail="Enter the six-digit code")
    if not consume_login_code(phone, code_hash(phone, payload.code)):
        raise HTTPException(status_code=401, detail="The code is invalid or expired")
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        SESSION_COOKIE,
        session_token(phone),
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=settings.public_base_url.startswith("https://"),
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/api/me/shipments")
def my_shipments(request: Request):
    phone = phone_from_session(request.cookies.get(SESSION_COOKIE))
    if not phone:
        raise HTTPException(status_code=401, detail="Authentication required")
    rows = list_shipments(phone)
    for row in rows:
        row.pop("user_phone", None)
        row["tracking_url"] = carrier_tracking_url(row["carrier"], row["tracking_number"])
    return {"shipments": rows}


@app.get("/login", response_class=HTMLResponse)
def customer_login(request: Request):
    if phone_from_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/app", status_code=303)
    return HTMLResponse(LOGIN_PAGE)


@app.get("/app", response_class=HTMLResponse)
def customer_app(request: Request):
    if not phone_from_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(APP_PAGE)


@app.get("/manifest.webmanifest")
def web_manifest():
    return JSONResponse({
        "name": "Package Tracker",
        "short_name": "Tracker",
        "start_url": "/app",
        "display": "standalone",
        "background_color": "#f5f6fa",
        "theme_color": "#1262c5",
        "icons": [{"src": "/app-icon.svg", "sizes": "any", "type": "image/svg+xml"}],
    }, media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return Response("self.addEventListener('fetch',()=>{});", media_type="application/javascript")


@app.get("/app-icon.svg")
def app_icon():
    return Response("""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'><rect width='512' height='512' rx='96' fill='#1262c5'/><path d='M104 158l152-76 152 76v196l-152 76-152-76z' fill='white'/><path d='M104 158l152 78 152-78M256 236v194' fill='none' stroke='#1262c5' stroke-width='24'/></svg>""", media_type="image/svg+xml")


@app.get("/.well-known/assetlinks.json")
def android_asset_links():
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.alekhyakusam.packagetracker",
            "sha256_cert_fingerprints": [
                "FA:20:A7:84:C0:AF:71:D7:FD:01:0A:CE:A4:08:06:CE:9A:7C:94:44:BF:24:F5:77:1D:52:FE:DD:48:AB:D1:A6"
            ],
        },
    }])


@app.get("/customer/{token}", response_class=HTMLResponse)
def customer_dashboard(token: str):
    if not phone_from_customer_token(token):
        raise HTTPException(status_code=404, detail="Customer dashboard not found")
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>My Package Tracker</title><style>body{{font:15px system-ui;margin:0;background:#f5f6fa;color:#172033}}main{{max-width:900px;margin:48px auto;padding:0 20px}}h1{{font-size:32px}}.card{{background:white;border-radius:16px;box-shadow:0 8px 30px #17203312;overflow:hidden}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:15px;border-bottom:1px solid #edf0f5}}th{{background:#fafbfc;color:#687386}}.status{{display:inline-block;padding:5px 9px;border-radius:99px;background:#e8f1ff;color:#1262c5}}@media(max-width:650px){{th,td{{padding:11px 8px}}}}</style></head>
<body><main><h1>My deliveries</h1><p>This private page only shows packages sent from your WhatsApp number.</p><div class='card'><table><thead><tr><th>Item</th><th>Carrier</th><th>Tracking</th><th>Status</th></tr></thead><tbody id='rows'></tbody></table></div></main>
<script>const e=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const tracking=x=>x.tracking_url?`<a href="${{e(x.tracking_url)}}" target="_blank" rel="noopener noreferrer">${{e(x.tracking_number)}} ↗</a>`:e(x.tracking_number);async function load(){{const d=await fetch('/api/customer/{token}/shipments').then(r=>r.json());document.querySelector('#rows').innerHTML=d.shipments.map(x=>`<tr><td>${{e(x.item_label)}}</td><td>${{e(x.carrier)}}</td><td>${{tracking(x)}}</td><td><span class=status>${{e(x.status)}}</span></td></tr>`).join('')||'<tr><td colspan=4>No deliveries yet.</td></tr>'}}load();setInterval(load,15000)</script></body></html>""")


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_auth)])
def dashboard():
    return HTMLResponse("""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Package Tracker</title><style>body{font:15px system-ui;margin:0;background:#f5f6fa;color:#172033}main{max-width:1050px;margin:48px auto;padding:0 20px}h1{font-size:32px}.card{background:white;border-radius:16px;box-shadow:0 8px 30px #17203312;overflow:hidden}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:15px;border-bottom:1px solid #edf0f5}th{background:#fafbfc;color:#687386}.status{display:inline-block;padding:5px 9px;border-radius:99px;background:#e8f1ff;color:#1262c5}@media(max-width:700px){th:nth-child(4),td:nth-child(4){display:none}}</style></head>
<body><main><h1>Your deliveries</h1><p>Forward a shipping message or screenshot to the WhatsApp bot. New deliveries appear here automatically.</p><div class='card'><table><thead><tr><th>Item</th><th>Carrier</th><th>Tracking</th><th>Customer</th><th>Status</th></tr></thead><tbody id='rows'></tbody></table></div></main>
<script>const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const tracking=x=>x.tracking_url?`<a href="${e(x.tracking_url)}" target="_blank" rel="noopener noreferrer" aria-label="Track ${e(x.tracking_number)} on ${e(x.carrier)}">${e(x.tracking_number)} ↗</a>`:e(x.tracking_number);async function load(){const d=await fetch('/api/shipments').then(r=>r.json());document.querySelector('#rows').innerHTML=d.shipments.map(x=>`<tr><td>${e(x.item_label)}</td><td>${e(x.carrier)}</td><td>${tracking(x)}</td><td>${e(x.user_phone)}</td><td><span class=status>${e(x.status)}</span></td></tr>`).join('')||'<tr><td colspan=5>No deliveries yet.</td></tr>'}load();setInterval(load,15000)</script></body></html>""")
