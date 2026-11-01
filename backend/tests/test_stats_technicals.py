import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.analytics import stats
from app.ingestion.providers.mock import MockProvider
from app.services import technicals as t

BARS = MockProvider(date(2026, 10, 23), 600).history("MSFT")


def days(n):
    return [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]


def test_window_stats_known_values():
    s = stats.window_stats(days(5), [100, 110, 99, 120, 108])
    assert math.isclose(s["total_return"], 0.08)
    assert math.isclose(s["max_drawdown"], 99 / 110 - 1, abs_tol=1e-6)
    assert s["best_day"]["return"] == pytest.approx(120 / 99 - 1, abs=1e-6) and s["worst_day"]["return"] == pytest.approx(-0.1, abs=1e-6)
    assert s["annualized_volatility"] is None and s["annualized_return"] is None  # too short: unavailable, not zero
    assert len(s["notes"]) == 2


def test_annualised_metrics_appear_with_enough_data():
    x = list(100 * np.cumprod(1 + np.random.default_rng(5).normal(0.0005, 0.01, 400)))
    s = stats.window_stats(days(400), x)
    assert s["annualized_volatility"] == pytest.approx(0.01 * math.sqrt(252), rel=0.2)
    assert s["annualized_return"] is not None and s["notes"] == []


def test_series_first_return_is_null_not_zero():
    out = stats.series(days(3), [100, 110, 121])
    assert out["daily_return"][0] is None and out["daily_return"][1] == pytest.approx(0.1)
    assert out["cumulative_return"][-1] == pytest.approx(0.21) and out["drawdown"] == [0.0, 0.0, 0.0]


def test_too_short_window():
    assert stats.window_stats(days(1), [1.0])["total_return"] is None


def run(**kw):
    args = dict(window_start=len(BARS) - 120, sma=[20, 50], ema=[12], rsi_period=14, macd_params=(12, 26, 9), bb_window=20, bb_k=2.0, atr_period=14)
    args.update(kw)
    return t.compute_technicals(BARS, **args)


def test_technicals_shapes_and_warmup_uses_full_history():
    r = run()
    n = 120
    assert len(r["days"]) == len(r["rsi"]) == len(r["sma"]["50"]) == len(r["macd"]["hist"]) == n
    assert r["sma"]["50"][0] is not None  # window starts after warm-up, so no leading gaps
    assert all(0 <= v <= 100 for v in r["rsi"])
    lo, mid, up = r["bollinger"]["lower"], r["bollinger"]["mid"], r["bollinger"]["upper"]
    assert all(a <= b <= c for a, b, c in zip(lo, mid, up))


def test_technicals_nulls_when_window_includes_warmup():
    r = run(window_start=0)
    assert r["sma"]["50"][0] is None and r["rsi"][0] is None


def test_parameters_change_results_and_are_echoed():
    a, b = run(rsi_period=14), run(rsi_period=5)
    assert a["rsi"] != b["rsi"] and b["parameters"]["rsi"] == 5
    assert run(bb_k=3.0)["bollinger"]["upper"][-1] > run(bb_k=1.0)["bollinger"]["upper"][-1]


@pytest.mark.parametrize("kw", [{"rsi_period": 1}, {"macd_params": (26, 12, 9)}, {"bb_window": 2}, {"bb_k": 9.0}, {"atr_period": 500}])
def test_invalid_parameters_rejected(kw):
    with pytest.raises(t.ParamError):
        run(**kw)


def test_parse_int_list_validation():
    assert t.parse_int_list("20, 50,20", "sma", 2, 400) == [20, 50]
    for raw in ("a,b", "1,2,3,4,5", "1000"):
        with pytest.raises(t.ParamError):
            t.parse_int_list(raw, "sma", 2, 400)
