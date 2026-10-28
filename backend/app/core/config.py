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

    @property
    def is_demo(self) -> bool:
        return self.data_provider == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
