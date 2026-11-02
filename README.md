# Order Tracking Bot

A production-oriented WhatsApp package tracker. Customers forward shipping text or screenshots; the service extracts carrier details, registers the shipment, persists its state, and sends delivery updates.

## Architecture

- **Ingress:** signed Twilio WhatsApp webhooks
- **Parsing:** deterministic carrier patterns first, OpenAI structured vision/text extraction as fallback
- **Tracking:** AfterShip Tracking API and signed update webhooks
- **Persistence:** PostgreSQL in production; SQLite for local development
- **Operations:** readiness/health checks, Prometheus metrics, structured logs, migrations, Docker, and CI
- **Dashboard:** disabled by default and protected with HTTP Basic authentication when enabled

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local
alembic upgrade head
uvicorn app.main:app --reload
```

Set the required values in `.env.local`. Never commit that file.

```bash
pytest -q
```

Local endpoints:

- `GET /health` — process liveness
- `GET /ready` — database readiness
- `GET /metrics` — Prometheus metrics
- `POST /webhooks/whatsapp` — signed Twilio ingress
- `POST /webhooks/aftership` — signed AfterShip updates
- `GET /` and `/api/shipments` — authenticated dashboard when enabled

## Production deployment

The included Docker image runs migrations before starting Gunicorn. Use a managed PostgreSQL database and configure these variables in the deployment platform:

```text
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
PUBLIC_BASE_URL=https://your-production-domain
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+...
AFTERSHIP_API_KEY=...
AFTERSHIP_WEBHOOK_SECRET=...
ENABLE_DASHBOARD=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<long-random-password>
METRICS_TOKEN=<long-random-token>
TWILIO_POLLING_ENABLED=false
```

Production startup fails fast when required settings are missing. If AfterShip is enabled, its webhook secret is mandatory. Polling mode is intentionally rejected in production because multiple replicas would process the same Twilio feed; use signed webhooks instead.

### Twilio

Configure the production WhatsApp sender's incoming message URL as:

```text
POST https://your-production-domain/webhooks/whatsapp
```

The service validates every `X-Twilio-Signature`. Use a registered WhatsApp sender for production; Twilio's trial testing environment restricts custom replies.

### AfterShip

Configure the tracking webhook as:

```text
POST https://your-production-domain/webhooks/aftership
```

Set the matching webhook secret in `AFTERSHIP_WEBHOOK_SECRET`. Incoming signatures are compared using constant-time HMAC validation.

## Deployment options

- `railway.toml` configures a Railway Docker deployment and `/ready` health check.
- `docker-compose.yml` provides an app/PostgreSQL stack for a controlled server.
- `.github/workflows/ci.yml` runs tests and builds the image on pushes and pull requests.

## Operational checklist

- Use managed PostgreSQL with automated backups and point-in-time recovery.
- Store all secrets in the hosting platform's encrypted variables.
- Put `/metrics` behind the platform's private network or access control.
- Set alerts for 5xx rate, webhook signature failures, queue latency, and database availability.
- Rotate Twilio, OpenAI, AfterShip, and dashboard credentials regularly.
- Configure at least two application replicas only after moving any background work to a dedicated worker.
- Review carrier data retention and customer privacy requirements for every launch region.

## Known account dependencies

Code readiness does not activate paid third-party capabilities. A real launch still requires:

1. A funded OpenAI API project for screenshot/ambiguous-message parsing.
2. A production Twilio WhatsApp sender approved by Meta/Twilio.
3. An AfterShip plan with Tracking API access, or an equivalent carrier aggregator.
4. A production hosting account, domain, PostgreSQL database, monitoring, and backup policy.
