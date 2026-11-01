from app.ingestion.providers.base import Instrument
from app.services.export import build_csv, csv_safe, filename
from app.services.search import search_instruments

ITEMS = [
    Instrument("AAPL", "Apple Inc.", "NASDAQ", "USD", "equity"),
    Instrument("AMD", "Advanced Micro Devices", "NASDAQ", "USD", "equity"),
    Instrument("AMZN", "Amazon.com, Inc.", "NASDAQ", "USD", "equity"),
    Instrument("SPY", "SPDR S&P 500 ETF (S&P 500 proxy)", "NYSE Arca", "USD", "index_proxy"),
    Instrument("TSLA", "Tesla, Inc.", "NASDAQ", "USD", "equity"),
]


def syms(q, **kw):
    return [r["symbol"] for r in search_instruments(ITEMS, q, **kw)]


def test_exact_symbol_beats_prefix_and_name():
    assert syms("amd")[0] == "AMD"
    assert syms("am") == ["AMD", "AMZN"]  # both symbol prefixes, alphabetical tie-break


def test_company_name_and_word_prefix_and_empty_results():
    assert syms("tesla") == ["TSLA"]
    assert syms("micro") == ["AMD"]
    assert syms("zzzz") == [] and syms("   ") == []


def test_limit_applies():
    assert len(syms("a", limit=2)) == 2


def test_csv_formula_injection_is_neutralised():
    for bad in ("=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tx", "\rx"):
        assert csv_safe(bad).startswith("'")
    assert csv_safe("AAPL") == "AAPL" and csv_safe(-1.5) == -1.5


def test_build_csv_metadata_and_rows():
    out = build_csv(["a", "b"], [("=evil", -2.5)], {"source": "mock (simulated)", "multi": "x\ny"})
    lines = out.splitlines()
    assert lines[0] == "# source: mock (simulated)" and lines[1] == "# multi: x y"
    assert lines[2] == "a,b" and lines[3] == "'=evil,-2.5"


def test_filename_is_safe():
    from datetime import date

    assert filename("A/B;C", "prices", "1Y", date(2026, 10, 23)) == "marketpulse_ABC_prices_1Y_2026-10-23.csv"
