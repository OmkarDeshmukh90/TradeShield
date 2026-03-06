from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TradeShield AI"
    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    api_prefix: str = "/v1"

    database_url: str = "sqlite:///./tradeshield.db"
    auto_create_schema: bool = True
    ingestion_interval_seconds: int = 900
    worker_poll_interval_seconds: int = 60
    request_timeout_seconds: int = 20
    health_ingestion_stale_minutes: int = 45
    enabled_connectors: str = "all"
    ingestion_error_backoff_minutes: int = 30
    ingestion_backoff_error_threshold: int = 3
    demo_mode: bool = False
    demo_scenario: Literal["tariff", "congestion", "all"] = "all"

    model_version: str = "ts-risk-v1.1.0"
    auth_secret: str = "change-me-dev-secret"
    access_token_ttl_minutes: int = 480
    password_hash_iterations: int = 390000
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    enable_docs: bool = True
    log_level: str = "INFO"

    alert_max_attempts: int = 5
    alert_retry_backoff_seconds: int = 60
    alert_batch_size: int = 50

    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    spire_api_key: str = Field(default="", alias="SPIRE_API_KEY")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: str = Field(default="", alias="TWILIO_WHATSAPP_FROM")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    smtp_use_starttls: bool = Field(default=True, alias="SMTP_USE_STARTTLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def get_cors_origins() -> list[str]:
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if origins:
        return origins
    return ["http://127.0.0.1:8000", "http://localhost:8000"]


def get_enabled_connectors() -> set[str] | None:
    raw = (settings.enabled_connectors or "all").strip().lower()
    if not raw or raw in {"all", "*"}:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}
