from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"
    public_base_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""
    aftership_api_key: str = ""
    aftership_webhook_secret: str = ""
    database_path: str = "data/forwarding_bot.db"
    enable_dashboard: bool = False
    twilio_polling_enabled: bool = False
    twilio_poll_interval_seconds: int = 5

    model_config = SettingsConfigDict(
        env_file=(".env.local", "../.env.local"), env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
