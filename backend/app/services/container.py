"""Process-wide singletons: repository, provider and ingestion service."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.ingestion.providers.base import MarketDataProvider
from app.ingestion.providers.mock import MockProvider
from app.ingestion.service import IngestionService
from app.storage.base import Repository
from app.storage.memory import MemoryRepository


@lru_cache
def get_provider() -> MarketDataProvider:
    s = get_settings()
    if s.data_provider == "mock":
        return MockProvider(s.demo_anchor_date, s.demo_history_days)
    raise RuntimeError(f"Unsupported data provider: {s.data_provider}")


@lru_cache
def get_repo() -> Repository:
    s = get_settings()
    if s.storage == "postgres":
        from app.storage.sql import SqlRepository  # imported lazily: needs sqlalchemy + psycopg

        return SqlRepository(s.database_url)
    return MemoryRepository()


@lru_cache
def get_ingestion() -> IngestionService:
    return IngestionService(get_provider(), get_repo())


def reset_for_tests() -> None:
    for fn in (get_provider, get_repo, get_ingestion):
        fn.cache_clear()
