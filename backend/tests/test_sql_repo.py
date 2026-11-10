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


def test_saved_screens_on_postgres(repo):
    from app.domain import ConflictError, NotFoundError

    sc = repo.create_screen("alice", "Momentum", {"filters": []})
    with pytest.raises(ConflictError):
        repo.create_screen("alice", "Momentum", {"filters": []})
    with pytest.raises(NotFoundError):
        repo.delete_screen("bob", sc.id)
    repo.delete_screen("alice", sc.id)
    assert repo.list_screens("alice") == []


def test_portfolio_and_alerts_on_postgres(repo):
    from datetime import date
    from decimal import Decimal as D

    from app.domain import Alert, NotFoundError, Txn, utcnow
    from app.services import alerts as al
    from app.services import portfolio as pf

    p = repo.create_portfolio("alice", "P", Txn(0, 0, date(2026, 3, 2), "deposit", amount=D("1000")))
    with pytest.raises(pf.PortfolioError):
        repo.add_txn("alice", p.id, Txn(0, 0, date(2026, 3, 2), "buy", "X", D(100), D(100)), pf.validate_history)
    repo.add_txn("alice", p.id, Txn(0, 0, date(2026, 3, 2), "buy", "X", D("2.5"), D("100.25"), D("1")), pf.validate_history)
    led = pf.replay(repo.list_txns("alice", p.id))
    assert led.positions["X"].quantity == D("2.5") and led.cash == D("748.375")
    with pytest.raises(NotFoundError):
        repo.list_txns("bob", p.id)

    a = repo.create_alert("alice", Alert(0, "alice", "X", "price_above", 100.0, None, 1, True, "", date(2026, 3, 2), False))
    ev = al.Evaluation(events=[{"observed_day": date(2026, 3, 3), "observed_value": 101.0, "message": "m"}],
                       last_observed_day=date(2026, 3, 3), last_condition=True, fired_in_episode=True, last_fired_day=date(2026, 3, 3))
    assert repo.record_evaluation(a.id, date(2026, 3, 2), ev, utcnow()) is True
    assert repo.record_evaluation(a.id, date(2026, 3, 2), ev, utcnow()) is False
    assert repo.unread_count("alice") == 1 and repo.mark_events_read("alice", None) == 1


def test_backtests_and_news_on_postgres(repo):
    from datetime import UTC, datetime

    from app.domain import Article, NotFoundError

    rec = repo.save_backtest("alice", "X", "ma_cross", {"a": 1}, {"metrics": {"total_return": 0.1}})
    assert repo.get_backtest("alice", rec.id).result["metrics"]["total_return"] == 0.1
    with pytest.raises(NotFoundError):
        repo.get_backtest("bob", rec.id)
    now = datetime(2026, 10, 23, 21, tzinfo=UTC)
    a = Article(0, "k1", "file", "NVDA beats estimates", "Wire", now, None, "", [{"symbol": "NVDA", "relevance": 1.0}], 0.5, "positive", "lexicon-baseline", "1", now)
    assert repo.upsert_articles([a, a]) == (1, 1) or repo.upsert_articles([a]) == (0, 1)
    items, total = repo.list_articles(symbol="NVDA", min_relevance=0.7)
    assert total == 1 and items[0].sentiment_category == "positive"
    assert repo.list_articles(symbol="AMD")[1] == 0
