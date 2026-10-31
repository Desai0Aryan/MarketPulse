import math

import numpy as np

from app.analytics import indicators as ind


def test_sma_known_values_and_warmup():
    out = ind.sma([1, 2, 3, 4, 5], 3)
    assert np.isnan(out[:2]).all()
    assert list(out[2:]) == [2.0, 3.0, 4.0]


def test_ema_seed_is_sma_and_recursion():
    x = [10, 11, 12, 13, 14, 15]
    out = ind.ema(x, 3)
    assert np.isnan(out[:2]).all()
    assert out[2] == 11.0  # SMA seed
    alpha = 0.5
    assert math.isclose(out[3], alpha * 13 + (1 - alpha) * 11.0)


def test_rsi_all_gains_is_100_and_flat_is_50():
    assert ind.rsi(np.arange(1, 40, dtype=float), 14)[-1] == 100.0
    assert ind.rsi(np.ones(40), 14)[-1] == 50.0


def test_rsi_bounds_and_warmup():
    rng = np.random.default_rng(1)
    x = 100 + np.cumsum(rng.normal(0, 1, 300))
    r = ind.rsi(x, 14)
    assert np.isnan(r[:14]).all() and not np.isnan(r[14:]).any()
    assert ((r[14:] >= 0) & (r[14:] <= 100)).all()


def test_rsi_matches_wilder_reference():
    # Classic worked example (Wilder / StockCharts) first RSI value ~ 70.46
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    assert math.isclose(ind.rsi(closes, 14)[14], 70.46, abs_tol=0.1)


def test_macd_relationship_and_order_check():
    rng = np.random.default_rng(2)
    x = 100 + np.cumsum(rng.normal(0, 1, 200))
    line, sig, hist = ind.macd(x)
    ok = ~np.isnan(hist)
    assert np.allclose(hist[ok], (line - sig)[ok])
    assert np.isnan(line[:25]).all() and not np.isnan(line[25])
    assert not np.isnan(sig[33]) and np.isnan(sig[32])


def test_bollinger_bands_symmetry_and_constant_series():
    lo, mid, up = ind.bollinger(np.full(30, 50.0), 20)
    assert np.allclose(lo[19:], 50) and np.allclose(up[19:], 50)
    x = np.arange(1.0, 41.0)
    lo, mid, up = ind.bollinger(x, 20)
    assert np.allclose(up[19:] - mid[19:], mid[19:] - lo[19:])


def test_atr_constant_range():
    n = 30
    out = ind.atr(np.full(n, 11.0), np.full(n, 9.0), np.full(n, 10.0), 14)
    assert np.isnan(out[:13]).all() and np.allclose(out[13:], 2.0)


def test_roc_returns_and_cumulative():
    x = np.array([100.0, 110.0, 121.0])
    assert math.isclose(ind.roc(x, 1)[1], 10.0)
    r = ind.returns(x)
    assert np.isnan(r[0]) and np.allclose(r[1:], 0.1)
    assert math.isclose(ind.cumulative_returns(x)[-1], 0.21)


def test_max_drawdown():
    assert math.isclose(ind.max_drawdown([100, 120, 90, 130, 117]), -0.25)
    assert ind.max_drawdown([1, 2, 3]) == 0.0


def test_rolling_vol_not_zero_filled():
    x = 100 * np.cumprod(1 + np.random.default_rng(3).normal(0, 0.01, 100))
    v = ind.rolling_volatility(x, 20)
    assert np.isnan(v[:20]).all() and (v[20:] > 0).all()


def test_no_lookahead_prefix_stability():
    """Indicator values on a prefix must equal the same positions on the full series."""
    rng = np.random.default_rng(4)
    x = 100 + np.cumsum(rng.normal(0, 1, 250))
    for fn in (lambda a: ind.sma(a, 20), lambda a: ind.ema(a, 12), lambda a: ind.rsi(a, 14), lambda a: ind.macd(a)[2]):
        full, prefix = fn(x), fn(x[:150])
        assert np.allclose(full[:150], prefix, equal_nan=True)
