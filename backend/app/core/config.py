from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MP_", env_file=".env", extra="ignore")

    app_name: str = "MarketPulse"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Data provider. "mock" is deterministic synthetic data and needs no API key.
    data_provider: str = "mock"
    demo_anchor_date: date = date(2026, 10, 23)  # last synthetic session
    demo_history_days: int = 1300  # ~5 years of sessions

    database_url: str = "postgresql+psycopg://marketpulse:marketpulse@localhost:5432/marketpulse"
    # "memory" needs no database (data resets on restart); "postgres" persists via SQLAlchemy.
    storage: str = "memory"
    auto_seed: bool = True  # on startup, backfill if the store is empty (demo provider only)

    # Operational endpoints (manual ingest/backfill). If set, requests need header X-Admin-Token.
    # If unset, they are allowed only when environment == "development".
    admin_token: str | None = None
    ingest_interval_minutes: int = 60  # worker schedule

    @property
    def is_demo(self) -> bool:
        return self.data_provider == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
