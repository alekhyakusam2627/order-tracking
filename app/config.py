from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    public_base_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""
    aftership_api_key: str = ""
    aftership_webhook_secret: str = ""
    database_url: str = ""
    database_path: str = "data/forwarding_bot.db"
    enable_dashboard: bool = False
    dashboard_username: str = "admin"
    dashboard_password: str = ""
    customer_dashboard_secret: str = ""
    metrics_token: str = ""
    twilio_polling_enabled: bool = False
    twilio_poll_interval_seconds: int = 5
    max_request_bytes: int = 2_000_000

    model_config = SettingsConfigDict(
        env_file=(".env.local", "../.env.local"), env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def production(self) -> bool:
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def validate_production(self):
        if not self.production:
            return self
        missing: list[str] = []
        for name in ("openai_api_key", "public_base_url", "twilio_auth_token", "database_url"):
            if not getattr(self, name):
                missing.append(name.upper())
        if self.enable_dashboard and not self.dashboard_password:
            missing.append("DASHBOARD_PASSWORD")
        if not self.customer_dashboard_secret:
            missing.append("CUSTOMER_DASHBOARD_SECRET")
        if not self.metrics_token:
            missing.append("METRICS_TOKEN")
        if self.aftership_api_key and not self.aftership_webhook_secret:
            missing.append("AFTERSHIP_WEBHOOK_SECRET")
        if self.twilio_polling_enabled:
            raise ValueError("TWILIO_POLLING_ENABLED must be false in production; use signed webhooks")
        if missing:
            raise ValueError(f"Missing required production settings: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
