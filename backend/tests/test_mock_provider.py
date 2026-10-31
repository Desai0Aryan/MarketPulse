from datetime import date

from app.ingestion.providers.mock import MockProvider


def test_mock_is_deterministic():
    a = MockProvider(date(2026, 10, 23), 300).history("NVDA")
    b = MockProvider(date(2026, 10, 23), 300).history("NVDA")
    assert a == b and len(a) == 300


def test_bars_are_valid_ohlc_for_whole_universe():
    p = MockProvider(date(2026, 10, 23), 500)
    for inst in p.instruments():
        for bar in p.history(inst.symbol):
            assert bar.low <= min(bar.open, bar.close) and bar.high >= max(bar.open, bar.close)
            assert bar.low > 0 and bar.volume >= 0
