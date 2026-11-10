import json
from datetime import UTC, datetime, timedelta

import pytest

from app.domain import NotFoundError
from app.ingestion.providers.base import Instrument
from app.ingestion.providers.mock import MockProvider
from app.services import news as nw
from app.storage.memory import MemoryRepository

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
INST = {"NVDA": Instrument("NVDA", "NVIDIA Corporation", "NASDAQ", "USD", "equity"),
        "AMD": Instrument("AMD", "Advanced Micro Devices", "NASDAQ", "USD", "equity")}


def raw(**kw):
    base = {"headline": "NVIDIA beats estimates as data-center demand grows", "source": "Example Wire", "published_at": "2026-10-23T14:30:00Z",
            "url": "https://example.com/a", "summary": "", "symbols": ["NVDA"]}
    return {**base, **kw}


def test_sentiment_baseline_directions_negation_and_determinism():
    assert nw.score_text("Shares surge after record profit")[1] == "positive"
    assert nw.score_text("Stock plunges on lawsuit and weak outlook")[1] == "negative"
    assert nw.score_text("Company schedules annual meeting")[0] == 0.0
    assert nw.score_text("Profit not strong this quarter")[0] < nw.score_text("Profit strong this quarter")[0]
    assert nw.score_text("Shares surge") == nw.score_text("Shares surge")
    for t in ("surge " * 50, "plunge " * 50):
        assert -1 <= nw.score_text(t)[0] <= 1


def test_relevance_levels():
    n, a = INST["NVDA"], INST["AMD"]
    assert nw.relevance(n, "NVDA climbs", "", False) == 1.0
    assert nw.relevance(n, "NVIDIA beats estimates", "", False) == 0.7
    assert nw.relevance(n, "Chipmakers rally", "NVIDIA was mentioned", False) == 0.4
    assert nw.relevance(n, "Chipmakers rally", "", True) == 0.3
    assert nw.relevance(a, "Chipmakers rally", "", False) is None


@pytest.mark.parametrize(
    "bad,reason",
    [({"headline": ""}, "missing headline"), ({"source": ""}, "source"), ({"published_at": "yesterday"}, "invalid published_at"),
     ({"published_at": "2026-10-23T14:30:00"}, "no timezone"), ({"published_at": "2027-01-01T00:00:00Z"}, "future"),
     ({"headline": "x" * 400}, "too long")],
)
def test_invalid_records_rejected_with_reason(bad, reason):
    res = nw.normalize(raw(**bad), INST, "file", NOW)
    assert isinstance(res, nw.Rejected) and reason in res.reason


def test_bad_url_dropped_but_article_kept_and_nothing_invented():
    a = nw.normalize(raw(url="javascript:alert(1)"), INST, "file", NOW)
    assert a.url is None and a.headline.startswith("NVIDIA") and a.source == "Example Wire"
    assert a.published_at == datetime(2026, 10, 23, 14, 30, tzinfo=UTC)
    assert {s["symbol"] for s in a.symbols} == {"NVDA"} and a.simulated is False


def test_dedup_key_ignores_case_punctuation_but_not_date():
    t = datetime(2026, 10, 23, 14, tzinfo=UTC)
    assert nw.dedup_key("NVIDIA Beats Estimates!", t) == nw.dedup_key("nvidia beats  estimates", t + timedelta(hours=2))
    assert nw.dedup_key("NVIDIA beats", t) != nw.dedup_key("NVIDIA beats", t + timedelta(days=1))


def test_file_provider_refresh_dedups_rejects_and_scores(tmp_path):
    p = tmp_path / "news.jsonl"
    lines = [json.dumps(raw()), json.dumps(raw(source="Other Wire")), json.dumps(raw(headline="AMD shares plunge on weak guidance", symbols=["AMD"])),
             "{not json", json.dumps(raw(headline="", symbols=[])), ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    repo = MemoryRepository()
    repo.upsert_instruments(list(INST.values()))
    out = nw.refresh(repo, nw.FileNewsProvider(str(p)), NOW)
    assert (out["inserted"], out["duplicates"], out["rejected"]) == (2, 1, 2) and out["simulated"] is False
    items, total = repo.list_articles()
    assert total == 2 and all(a.sentiment_method == "lexicon-baseline" and a.sentiment_version == "1" and a.sentiment_at for a in items)
    again = nw.refresh(repo, nw.FileNewsProvider(str(p)), NOW)
    assert again["inserted"] == 0 and again["duplicates"] == 3  # idempotent
    assert repo.list_articles()[1] == 2


def test_missing_file_is_an_error_not_an_empty_result(tmp_path):
    with pytest.raises(FileNotFoundError):
        nw.FileNewsProvider(str(tmp_path / "nope.jsonl")).fetch()


def seeded():
    repo = MemoryRepository()
    p = MockProvider(__import__("datetime").date(2026, 10, 23), 400)
    repo.upsert_instruments(p.instruments())
    for i in p.instruments():
        repo.upsert_bars(i.symbol, p.history(i.symbol), None)
    return repo


def test_sample_feed_is_honestly_labelled_and_tied_to_stored_moves():
    repo = seeded()
    out = nw.refresh(repo, nw.SampleNewsProvider(repo, sessions=300, min_move_pct=2.5), NOW)
    assert out["simulated"] is True and out["inserted"] > 0
    items, _ = repo.list_articles(limit=500)
    for a in items:
        assert a.simulated and a.source == nw.SAMPLE_SOURCE and a.url is None and "Simulated" in a.summary
    a = items[0]
    sym = a.symbols[0]["symbol"]
    day = a.published_at.date()
    bars = {b.day: b for b in repo.get_bars(sym)}
    prev = max(d for d in bars if d < day)
    pct = float(__import__("re").search(r"(\d+\.\d)%", a.headline).group(1))
    assert pct == pytest.approx(abs((bars[day].close / bars[prev].close - 1) * 100), abs=0.06)  # headline matches the stored move
    assert a.published_at.hour == 21 and (a.sentiment_category == "positive") == ("surges" in a.headline or "rises" in a.headline)


def test_filters_symbol_source_date_relevance_sentiment():
    repo = MemoryRepository()
    repo.upsert_instruments(list(INST.values()))
    rows = [raw(), raw(headline="AMD shares plunge on weak guidance", symbols=["AMD"], source="Other Wire", published_at="2026-10-20T10:00:00Z"),
            raw(headline="Chipmakers rally broadly", symbols=["NVDA", "AMD"], published_at="2026-10-22T10:00:00Z")]
    for r in rows:
        repo.upsert_articles([nw.score_article(nw.normalize(r, INST, "file", NOW), NOW)])
    assert repo.list_articles(symbol="AMD")[1] == 2
    assert repo.list_articles(symbol="AMD", min_relevance=0.7)[1] == 1
    assert repo.list_articles(source="Other Wire")[1] == 1
    assert repo.list_articles(start=datetime(2026, 10, 22, tzinfo=UTC))[1] == 2
    assert repo.list_articles(sentiment="negative")[1] == 1
    items, _ = repo.list_articles()
    assert [a.published_at for a in items] == sorted((a.published_at for a in items), reverse=True)
    assert repo.list_sources()[0] == ("Example Wire", 2)
    s = nw.sentiment_summary(items)
    assert s["articles"] == 3 and "not a reliable predictor" in s["notice"]


def test_backtest_persistence_is_owner_scoped():
    repo = MemoryRepository()
    rec = repo.save_backtest("alice", "X", "ma_cross", {"a": 1}, {"metrics": {"total_return": 0.1}})
    assert repo.get_backtest("alice", rec.id).config == {"a": 1} and repo.list_backtests("bob") == []
    with pytest.raises(NotFoundError):
        repo.get_backtest("bob", rec.id)
    with pytest.raises(NotFoundError):
        repo.delete_backtest("bob", rec.id)
    repo.delete_backtest("alice", rec.id)
    assert repo.list_backtests("alice") == []
