from datetime import date

import pytest

from app.ingestion.providers.base import Bar
from app.ingestion.providers.mock import MockProvider
from app.ingestion.retry import ProviderError, RetryPolicy, call_with_retry
from app.ingestion.service import IngestionService, JobBusyError
from app.processing.quality import quality_report
from app.storage.memory import MemoryRepository

ANCHOR = date(2026, 10, 23)
NOSLEEP = lambda _s: None  # noqa: E731


def make(provider=None, repo=None):
    provider = provider or MockProvider(ANCHOR, 300)
    repo = repo or MemoryRepository()
    return IngestionService(provider, repo, policy=RetryPolicy(max_attempts=3), sleep=NOSLEEP), repo, provider


def test_backfill_is_idempotent():
    svc, repo, _ = make()
    r1 = svc.run("backfill", ["AAPL", "MSFT"])
    assert r1.status == "success" and r1.stats["inserted"] == 600
    count = repo.bar_counts()["AAPL"][0]
    r2 = svc.run("backfill", ["AAPL", "MSFT"])
    assert r2.stats["inserted"] == 0 and r2.stats["unchanged"] == 600  # duplicate attempts counted, not stored
    assert repo.bar_counts()["AAPL"][0] == count == 300


def test_incremental_fetches_only_new_bars_after_checkpoint():
    svc, repo, _ = make()
    svc.run("backfill", ["NVDA"], end=date(2026, 10, 9))
    cp = repo.get_checkpoint("NVDA")
    assert cp and cp.last_day == date(2026, 10, 9)
    r = svc.run("incremental", ["NVDA"])
    info = r.stats["per_symbol"]["NVDA"]
    assert info["inserted"] == 10  # sessions 10/12 .. 10/23
    assert info["fetched"] < 20  # lookback window only, not full history
    assert repo.get_checkpoint("NVDA").last_day == ANCHOR


def test_checkpoint_never_moves_backwards():
    svc, repo, _ = make()
    svc.run("backfill", ["AMD"])
    svc.run("backfill", ["AMD"], start=date(2026, 1, 5), end=date(2026, 2, 5))
    assert repo.get_checkpoint("AMD").last_day == ANCHOR


def test_indicators_are_written_and_match_bar_count():
    svc, repo, _ = make()
    svc.run("backfill", ["TSLA"])
    rows = repo.get_indicators("TSLA")
    assert len(rows) == 300
    assert rows[0]["sma20"] is None and rows[19]["sma20"] is not None
    assert rows[199]["sma200"] is not None and rows[198]["sma200"] is None


class CorrectingProvider(MockProvider):
    """Provider that later revises one historical close (e.g. a data vendor correction)."""

    def __init__(self, *a):
        super().__init__(*a)
        self.revise = False

    def history(self, symbol, start=None, end=None):
        bars = super().history(symbol, start, end)
        if not self.revise:
            return bars
        out = []
        for b in bars:
            if b.day == date(2026, 9, 1):
                b = Bar(b.day, b.open, b.high, b.low, round(b.close * 1.01, 2), round(b.close * 1.01, 2), b.volume)
                b = Bar(b.day, b.open, max(b.high, b.close), b.low, b.close, b.adj_close, b.volume)
            out.append(b)
        return out


def test_historical_correction_updates_row_and_recomputes_indicators_from_that_day():
    p = CorrectingProvider(ANCHOR, 300)
    svc, repo, _ = make(p)
    svc.run("backfill", ["JPM"])
    before = {r["day"]: r for r in repo.get_indicators("JPM")}
    p.revise = True
    r = svc.run("backfill", ["JPM"], start=date(2026, 8, 1))
    assert r.stats["updated"] == 1 and r.stats["inserted"] == 0
    after = {r["day"]: r for r in repo.get_indicators("JPM")}
    assert after[date(2026, 9, 2)]["sma20"] != before[date(2026, 9, 2)]["sma20"]  # affected
    assert after[date(2026, 8, 28)] == before[date(2026, 8, 28)]  # earlier rows untouched
    assert any("corrected" in e["msg"] for e in r.events)


class FlakyProvider(MockProvider):
    def __init__(self, *a, fail_times=2, dead=()):
        super().__init__(*a)
        self.fail_times, self.calls, self.dead = fail_times, {}, set(dead)

    def history(self, symbol, start=None, end=None):
        self.calls[symbol] = self.calls.get(symbol, 0) + 1
        if symbol in self.dead:
            raise ProviderError("HTTP 500", retryable=True)
        if self.calls[symbol] <= self.fail_times and symbol == "AAPL":
            raise ProviderError("HTTP 429", retryable=True)
        return super().history(symbol, start, end)


def test_transient_failures_are_retried():
    p = FlakyProvider(ANCHOR, 100, fail_times=2)
    svc, _, _ = make(p)
    r = svc.run("backfill", ["AAPL"])
    assert r.status == "success" and r.stats["retries"] == 2 and p.calls["AAPL"] == 3


def test_partial_failure_does_not_abort_other_symbols():
    p = FlakyProvider(ANCHOR, 100, fail_times=0, dead=["AMD"])
    svc, repo, _ = make(p)
    r = svc.run("backfill", ["AMD", "MSFT"])
    assert r.status == "partial" and r.stats["symbols_failed"] == 1 and r.stats["symbols_ok"] == 1
    assert "HTTP 500" in r.stats["per_symbol"]["AMD"]["error"]
    assert repo.bar_counts()["MSFT"][0] == 100
    assert r.stats["retries"] == 2  # max_attempts=3 -> 2 retries before giving up


def test_all_failed_status():
    p = FlakyProvider(ANCHOR, 50, dead=["AMD"])
    svc, _, _ = make(p)
    assert svc.run("backfill", ["AMD"]).status == "failed"


def test_non_retryable_error_is_not_retried():
    calls = []

    def boom():
        calls.append(1)
        raise ProviderError("401", retryable=False)

    with pytest.raises(ProviderError):
        call_with_retry(boom, RetryPolicy(max_attempts=5), sleep=NOSLEEP)
    assert len(calls) == 1


def test_backoff_delays_grow_and_are_capped():
    delays = []

    def boom():
        raise ProviderError("x")

    with pytest.raises(ProviderError):
        call_with_retry(boom, RetryPolicy(max_attempts=5, base_delay=1, max_delay=3), sleep=delays.append, rng=lambda: 1.0)
    assert delays == [1, 2, 3, 3]


def test_validation_failures_are_persisted_and_reported():
    class BadProvider(MockProvider):
        def history(self, symbol, start=None, end=None):
            bars = super().history(symbol, start, end)
            b = bars[5]
            bars[5] = Bar(b.day, b.open, b.high, b.low, -1.0, -1.0, b.volume)
            return bars

    svc, repo, p = make(BadProvider(ANCHOR, 50))
    r = svc.run("backfill", ["IWM"])
    assert r.stats["rejected"] == 1 and repo.bar_counts()["IWM"][0] == 49
    q = quality_report(repo, p.reference_day())
    assert q["rejected_records"] == 1 and q["rejections_by_reason"]["error:nonpositive_price"] == 1


def test_unknown_symbol_and_bad_range_are_rejected_up_front():
    svc, _, _ = make()
    with pytest.raises(ValueError):
        svc.run("backfill", ["NOPE"])
    with pytest.raises(ValueError):
        svc.run("backfill", ["AAPL"], start=date(2026, 5, 1), end=date(2026, 4, 1))
    assert not svc.busy  # failed validation must not leak the job lock


def test_duplicate_job_is_blocked_while_running():
    svc, _, _ = make()
    run = svc.begin("backfill", ["AAPL"], None, None, "manual")
    with pytest.raises(JobBusyError):
        svc.begin("backfill", ["MSFT"], None, None, "manual")
    svc.execute(run)
    assert not svc.busy


def test_reindex_rebuilds_indicators():
    svc, repo, _ = make()
    svc.run("backfill", ["XOM"])
    repo.replace_indicators("XOM", date.min, [])
    assert repo.get_indicators("XOM") == []
    svc.run("reindex", ["XOM"])
    assert len(repo.get_indicators("XOM")) == 300


def test_quality_report_stale_detection():
    svc, repo, p = make()
    svc.run("backfill", ["JNJ"], end=date(2026, 10, 1))
    q = quality_report(repo, p.reference_day())
    assert "JNJ" in q["stale_symbols"] and q["latest_timestamp"] == "2026-10-01"
