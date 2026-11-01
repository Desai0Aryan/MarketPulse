"""PostgreSQL integration tests. Skipped unless MP_TEST_DATABASE_URL points at a disposable database:

    MP_TEST_DATABASE_URL=postgresql+psycopg://marketpulse:marketpulse@localhost:5432/marketpulse_test pytest tests/test_sql_repo.py

They apply the Alembic migration, so they also verify the migration matches the ORM models.
"""

import os
from datetime import date

import pytest

URL = os.environ.get("MP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="MP_TEST_DATABASE_URL not set")


@pytest.fixture()
def repo():
    from alembic import command
    from alembic.config import Config

    os.environ["MP_DATABASE_URL"] = URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from app.storage.sql import SqlRepository

    return SqlRepository(URL)


def test_ingestion_is_idempotent_on_postgres(repo):
    from app.ingestion.providers.mock import MockProvider
    from app.ingestion.service import IngestionService

    svc = IngestionService(MockProvider(date(2026, 10, 23), 260), repo)
    r1 = svc.run("backfill", ["AAPL", "SPY"])
    assert r1.status == "success" and r1.stats["inserted"] == 520
    r2 = svc.run("backfill", ["AAPL", "SPY"])
    assert r2.stats["inserted"] == 0 and r2.stats["unchanged"] == 520
    assert repo.bar_counts()["AAPL"][0] == 260
    assert len(repo.get_indicators("AAPL")) == 260
    assert repo.get_checkpoint("AAPL").last_day == date(2026, 10, 23)


def test_correction_updates_row_and_checkpoint_never_rewinds(repo):
    from app.ingestion.providers.base import Bar
    from app.ingestion.providers.mock import MockProvider

    repo.upsert_instruments(MockProvider(date(2026, 10, 23), 10).instruments())
    b = Bar(date(2026, 10, 1), 10, 11, 9, 10.5, 10.5, 100)
    assert repo.upsert_bars("AAPL", [b], None).inserted == 1
    fixed = Bar(b.day, 10, 11, 9, 10.7, 10.7, 100)
    res = repo.upsert_bars("AAPL", [fixed], None)
    assert res.updated == 1 and repo.get_bars("AAPL")[0].close == 10.7
    repo.set_checkpoint("AAPL", date(2026, 10, 10), None)
    repo.set_checkpoint("AAPL", date(2026, 9, 1), None)
    assert repo.get_checkpoint("AAPL").last_day == date(2026, 10, 10)


def test_db_rejects_invalid_ohlc_even_if_app_validation_is_bypassed(repo):
    from sqlalchemy.exc import IntegrityError

    from app.ingestion.providers.base import Bar
    from app.ingestion.providers.mock import MockProvider

    repo.upsert_instruments(MockProvider(date(2026, 10, 23), 10).instruments())
    with pytest.raises(IntegrityError):
        repo.upsert_bars("AAPL", [Bar(date(2026, 10, 1), 10, 5, 9, 10, 10, 1)], None)  # high < low
    assert repo.get_bars("AAPL") == []  # transaction rolled back


def test_watchlists_on_postgres(repo):
    import pytest as _pytest

    from app.domain import ConflictError, NotFoundError
    from app.ingestion.providers.mock import MockProvider

    repo.upsert_instruments(MockProvider(date(2026, 10, 23), 10).instruments())
    a = repo.create_watchlist("alice", "Tech")
    b = repo.create_watchlist("alice", "Energy")
    assert a.is_default and not b.is_default
    with _pytest.raises(ConflictError):
        repo.create_watchlist("alice", "Tech")
    repo.add_watchlist_item("alice", a.id, "AAPL")
    repo.add_watchlist_item("alice", a.id, "MSFT")
    repo.add_watchlist_item("alice", a.id, "AAPL")  # idempotent
    assert repo.reorder_watchlist("alice", a.id, ["MSFT", "AAPL"]).symbols == ["MSFT", "AAPL"]
    repo.update_watchlist("alice", b.id, make_default=True)
    assert [w.is_default for w in repo.list_watchlists("alice")] == [False, True]
    with _pytest.raises(NotFoundError):  # another owner can neither see nor modify it
        repo.add_watchlist_item("mallory", a.id, "TSLA")
    assert repo.list_watchlists("mallory") == []
    repo.delete_watchlist("alice", b.id)  # deleting the default promotes the remaining list
    assert repo.list_watchlists("alice")[0].is_default
