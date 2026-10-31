from datetime import date

import pytest

from app.ingestion.providers.base import Bar
from app.processing.validation import normalize_bar, normalize_symbol, validate_bars


def bar(day, o=10, h=11, l=9, c=10.5, v=1000, adj=None):  # noqa: E741
    return Bar(day, o, h, l, c, adj if adj is not None else c, v)


def codes(res):
    return [r.code for r in res.rejected]


def test_valid_batch_is_accepted():
    res = validate_bars("X", [bar(date(2026, 1, 5)), bar(date(2026, 1, 6))])
    assert len(res.accepted) == 2 and not res.rejected and not res.warnings


def test_invalid_records_are_recorded_not_dropped_silently():
    batch = [
        bar(date(2026, 1, 5), o=-1),
        bar(date(2026, 1, 6), h=8),  # high below low/open/close
        bar(date(2026, 1, 7), v=-5),
        bar(date(2026, 1, 8), c=float("nan")),
        bar(date(2026, 1, 9)),
    ]
    res = validate_bars("X", batch)
    assert codes(res) == ["nonpositive_price", "invalid_ohlc", "negative_volume", "non_finite_price"]
    assert len(res.accepted) == 1 and all(r.detail for r in res.rejected)


def test_duplicate_and_out_of_order():
    res = validate_bars("X", [bar(date(2026, 1, 6)), bar(date(2026, 1, 6)), bar(date(2026, 1, 5)), bar(date(2026, 1, 7))])
    assert codes(res) == ["duplicate_timestamp", "out_of_order"]
    assert [b.day.day for b in res.accepted] == [6, 7]


def test_unexpected_jump_is_warning_but_kept():
    res = validate_bars("X", [bar(date(2026, 1, 5), c=10.5), bar(date(2026, 1, 6), o=15, h=17, l=14, c=16)], prev_close=None)
    assert len(res.accepted) == 2 and [w.code for w in res.warnings] == ["unexpected_jump"]


def test_adjusted_price_above_close_warns():
    res = validate_bars("X", [bar(date(2026, 1, 5), c=10, h=11, adj=12)])
    assert len(res.accepted) == 1 and res.warnings[0].code == "inconsistent_adjusted_price"


def test_normalize_aliases_and_epoch():
    b = normalize_bar({"t": 1767571200, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "100"})
    assert b.day == date(2026, 1, 5) and b.adj_close == 1.5 and b.volume == 100
    b2 = normalize_bar({"Date": "2026-01-06", "Open": 1, "High": 2, "Low": 1, "Close": 2, "Adj Close": 1.9, "Volume": 5})
    assert b2.adj_close == 1.9


def test_normalize_missing_and_bad_fields():
    with pytest.raises(ValueError, match="missing_field:close"):
        normalize_bar({"date": "2026-01-05", "open": 1, "high": 2, "low": 1, "volume": 1})
    with pytest.raises(ValueError, match="bad_value"):
        normalize_bar({"date": "nope", "open": 1, "high": 2, "low": 1, "close": 1, "volume": 1})


def test_symbol_normalisation():
    assert normalize_symbol(" brk.b ") == "BRK.B"
    with pytest.raises(ValueError):
        normalize_symbol("DROP TABLE;")
