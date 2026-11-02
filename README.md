# WhatsApp Forwarding Bot

Forward a shipment message or screenshot to a Twilio WhatsApp number. The service extracts tracking details with OpenAI, registers the shipment with AfterShip, stores it in SQLite, shows it on a dashboard, and sends WhatsApp status updates.

## Run locally

```bash
cd forwarding-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The service reads the workspace-level `.env.local` created during secure API setup. Copy the remaining names from `.env.example` into that file and add your Twilio and AfterShip credentials.

## Connect the services

1. Expose the local server with a secure HTTPS tunnel or deploy it.
2. Set `PUBLIC_BASE_URL` to that public origin (no trailing slash).
3. In the Twilio WhatsApp sender or Sandbox, set **A message comes in** to `POST https://your-domain/webhooks/whatsapp`.
4. In AfterShip, create a webhook pointing to `POST https://your-domain/webhooks/aftership` and set the same secret in `AFTERSHIP_WEBHOOK_SECRET`.
5. Set `ENABLE_DASHBOARD=true` only on a private or authenticated deployment, then open `/` for the delivery dashboard. `/health` remains available for health checks.

If `AFTERSHIP_API_KEY` is omitted, parsed shipments are still saved with a pending-registration status, which is useful for local testing.

For Twilio's newer trial console, which may not expose a custom inbound webhook, set
`TWILIO_POLLING_ENABLED=true`. The service then consumes received WhatsApp messages from
Twilio's API every few seconds and sends the same replies without requiring a public webhook.

## Production notes

- The dashboard is disabled by default. Put it behind authentication before enabling it on a public deployment.
- Use Postgres instead of SQLite when running multiple server instances.
- Keep `.env.local` out of source control and rotate any credential that is accidentally exposed.
