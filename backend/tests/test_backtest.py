from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from app.ingestion.providers.base import Bar
from app.ingestion.providers.mock import MockProvider
from app.services import backtest as bt

D0 = date(2024, 1, 1)
MSFT = MockProvider(date(2026, 10, 23), 900).history("MSFT")


def mk(closes, adj_factor=1.0, start=D0):
    out = []
    for i, c in enumerate(closes):
        c = float(c)
        out.append(Bar(start + timedelta(days=i), c * 0.99, c * 1.01, c * 0.98, c, c * adj_factor, 1000))
    return out


def cfg(**kw):
    base = dict(symbol="X", strategy="ma_cross", params={"fast": 3, "slow": 6}, commission_bps=0.0, slippage_bps=0.0)
    return bt.Config(**{**base, **kw})


def wave(n=200, seed=1):
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))))


# ---------------- validation ----------------
@pytest.mark.parametrize(
    "kw",
    [dict(params={"fast": 50, "slow": 20}), dict(params={"fast": 5, "slow": 5}), dict(params={"fast": 1, "slow": 9}), dict(params={"fast": 3, "slow": 6, "x": 1}),
     dict(strategy="rsi", params={"buy_below": 60, "sell_above": 40}), dict(strategy="rsi", params={"period": 1}), dict(strategy="momentum", params={"lookback": 2}),
     dict(strategy="nope"), dict(initial_capital=-5), dict(initial_capital=float("nan")), dict(commission_bps=9999), dict(slippage_bps=-1),
     dict(long_only=False), dict(sizing="kelly"), dict(sizing="fraction", fraction=0), dict(start=date(2025, 1, 1), end=date(2024, 1, 1)),
     dict(params={"fast": 3.5, "slow": 6})],
)
def test_invalid_configs_rejected(kw):
    with pytest.raises(bt.BacktestError):
        bt.run(mk(wave()), cfg(**kw))


def test_too_short_range_rejected():
    with pytest.raises(bt.BacktestError, match="at least"):
        bt.run(mk(wave(20)), cfg())


# ---------------- look-ahead / execution convention ----------------
def test_fills_happen_at_next_open_not_signal_close():
    closes = [100.0] * 20 + [100 + 3 * k for k in range(1, 30)]  # fast SMA crosses above slow shortly after the ramp starts
    bars = mk(closes)
    r = bt.run(bars, cfg(slippage_bps=10.0))
    t = r["trades"][0]
    entry_i = [b.day.isoformat() for b in bars].index(t["entry_day"])
    adj = np.array([b.adj_close for b in bars])
    sig = bt.target_position("ma_cross", {"fast": 3, "slow": 6}, adj)
    first_signal = int(np.argmax(sig > 0))
    assert entry_i == first_signal + 1  # executed the session AFTER the signal
    assert t["entry_price"] == pytest.approx(bars[entry_i].open * 1.001, abs=1e-3)  # next open + 10 bps adverse slippage
    assert t["entry_price"] != pytest.approx(bars[first_signal].close, abs=0.5)


@pytest.mark.parametrize("strategy,params", [("ma_cross", {"fast": 5, "slow": 20}), ("rsi", {"period": 7, "buy_below": 40, "sell_above": 60}), ("momentum", {"lookback": 10, "threshold_pct": 0})])
def test_future_data_cannot_change_past_results(strategy, params):
    base = mk(wave(260, seed=4))
    m = 150
    changed = base[: m + 1] + [replace(b, open=b.open * 3, high=b.high * 3, low=b.low * 3, close=b.close * 3, adj_close=b.adj_close * 3) for b in base[m + 1 :]]
    c = cfg(strategy=strategy, params=params, slippage_bps=5.0, commission_bps=5.0)
    a, b = bt.run(base, c), bt.run(changed, c)
    k = len(a["days"][: a["days"].index(base[m].day.isoformat()) + 1])
    # decisions through day m only depend on data through m, and execute at m+1's open, which we kept -> equity through m is identical
    assert a["equity"][:k] == b["equity"][:k]
    early = [t for t in a["trades"] if t["exit_day"] and t["exit_day"] <= base[m].day.isoformat()]
    assert early == [t for t in b["trades"] if t["exit_day"] and t["exit_day"] <= base[m].day.isoformat()]


def test_truncating_the_end_does_not_alter_earlier_equity():
    bars = mk(wave(300, seed=9))
    full = bt.run(bars, cfg(params={"fast": 5, "slow": 20}))
    part = bt.run(bars[:220], cfg(params={"fast": 5, "slow": 20}))
    n = len(part["equity"])
    assert full["equity"][:n] == part["equity"]


def test_signal_on_last_bar_is_discarded():
    closes = [100.0] * 40 + [90.0, 90, 90, 90, 90, 90, 90, 90, 90, 90, 200.0]  # last bar flips the signal
    r = bt.run(mk(closes), cfg(params={"fast": 3, "slow": 6}))
    assert all(t["entry_day"] != r["days"][-1] for t in r["trades"])


def test_warmup_holds_cash():
    r = bt.run(mk(wave(120)), cfg(params={"fast": 10, "slow": 60}))
    first = min((t["entry_day"] for t in r["trades"]), default=None)
    if first:
        assert r["days"].index(first) >= 60  # cannot trade before the slow SMA exists
    assert r["equity"][0] == 10_000.0


def test_start_date_respected_and_history_before_start_used_for_warmup():
    bars = mk(wave(300, seed=2))
    start = bars[150].day
    r = bt.run(bars, cfg(params={"fast": 5, "slow": 50}, start=start))
    assert r["days"][0] == start.isoformat() and all(t["entry_day"] >= start.isoformat() for t in r["trades"])


# ---------------- accounting ----------------
def test_equity_identity_with_costs_and_open_position():
    bars = mk(wave(260, seed=7))
    r = bt.run(bars, cfg(params={"fast": 5, "slow": 20}, commission_bps=25.0, slippage_bps=15.0))
    pnl = sum(t["pnl"] for t in r["trades"])  # includes the open trade's mark-to-market
    assert r["final_equity"] == pytest.approx(10_000 + pnl, abs=0.05 * (len(r["trades"]) + 1))
    assert r["metrics"]["completed_trades"] == sum(1 for t in r["trades"] if not t["open"])
    assert min(r["equity"]) > 0


def test_costs_reduce_results_monotonically():
    bars = mk(wave(300, seed=3))
    finals = [bt.run(bars, cfg(params={"fast": 4, "slow": 12}, commission_bps=c, slippage_bps=c))["final_equity"] for c in (0, 10, 50, 200)]
    assert finals == sorted(finals, reverse=True) and finals[0] > finals[-1]


def test_round_trip_cost_arithmetic():
    closes = [100.0] * 30 + [110.0] * 10 + [100.0] * 30
    bars = mk(closes)
    r = bt.run(bars, cfg(params={"fast": 2, "slow": 5}, commission_bps=100.0, slippage_bps=0.0, initial_capital=10_000))
    t = r["trades"][0]
    spent = 10_000  # full sizing: all cash incl. 1% commission
    qty = spent / (t["entry_price"] * 1.01)
    assert t["qty"] == pytest.approx(qty, rel=1e-5)
    assert t["pnl"] == pytest.approx(qty * t["exit_price"] * 0.99 - spent, abs=0.02)


def test_fraction_sizing_invests_only_that_share():
    bars = mk([100.0] * 20 + [100 + 2 * k for k in range(40)])
    r = bt.run(bars, cfg(params={"fast": 3, "slow": 6}, sizing="fraction", fraction=0.25))
    t = r["trades"][0]
    assert t["qty"] * t["entry_price"] == pytest.approx(2_500, rel=0.01)


def test_uses_adjusted_basis_consistently():
    plain = mk(wave(200, seed=5))
    scaled = mk(wave(200, seed=5), adj_factor=0.5)  # adjusted series is exactly half; returns must be identical
    a = bt.run(plain, cfg(params={"fast": 5, "slow": 20}))
    b = bt.run(scaled, cfg(params={"fast": 5, "slow": 20}))
    assert a["equity"] == pytest.approx(b["equity"], rel=1e-6)
    assert b["trades"][0]["entry_price"] == pytest.approx(a["trades"][0]["entry_price"] * 0.5, rel=1e-6)  # fills on the adjusted open


def test_buy_and_hold_reference_and_exposure():
    bars = mk([100 * 1.002**k for k in range(120)])
    r = bt.run(bars, cfg(strategy="momentum", params={"lookback": 5, "threshold_pct": 0}))
    assert r["buy_hold"][0] == 10_000 and r["metrics"]["exposure"] > 0.9
    assert r["metrics"]["total_return"] == pytest.approx(r["buy_hold_metrics"]["total_return"], abs=0.03)
    assert r["metrics"]["completed_trades"] == 0 and "No completed trades" in " ".join(r["metrics"]["notes"])


def test_rsi_strategy_is_stateful_and_trades():
    bars = mk(wave(400, seed=11))
    r = bt.run(bars, cfg(strategy="rsi", params={"period": 7, "buy_below": 35, "sell_above": 60}))
    assert r["trades"] and all(t["entry_day"] < (t["exit_day"] or "9999") for t in r["trades"])
    sig = bt.target_position("rsi", {"period": 7, "buy_below": 35, "sell_above": 60}, np.array([b.adj_close for b in bars]))
    assert set(np.unique(sig)) <= {0.0, 1.0}


def test_metrics_gating_and_sharpe_formula():
    short = bt.run(mk(wave(100, seed=1)), cfg())
    assert short["metrics"]["annualized_return"] is None and any("252" in n for n in short["metrics"]["notes"])
    long = bt.run(mk(wave(400, seed=1)), cfg(risk_free_pct=2.0))
    eq = np.array(long["equity"])
    r = eq[1:] / eq[:-1] - 1
    expect = (r.mean() - 0.02 / 252) / r.std(ddof=1) * np.sqrt(252)
    assert long["metrics"]["sharpe"] == pytest.approx(expect, abs=1e-3) and long["metrics"]["annualized_return"] is not None
    assert long["metrics"]["max_drawdown"] <= 0


def test_reproducible_and_records_assumptions():
    bars = MSFT
    c = cfg(symbol="MSFT", params={"fast": 20, "slow": 50}, commission_bps=5, slippage_bps=5)
    a, b = bt.run(bars, c), bt.run(bars, c)
    for k in ("equity", "trades", "metrics", "reproducibility"):
        assert a[k] == b[k]
    rep = a["reproducibility"]
    assert rep["strategy_version"] == bt.STRATEGY_VERSION and len(rep["data_fingerprint"]) == 16 and len(rep["assumptions"]) >= 5
    assert a["execution_ms"] >= 0 and a["config"]["params"] == {"fast": 20, "slow": 50}


def test_gap_and_short_sample_warnings():
    days = [D0 + timedelta(days=i) for i in range(40)] + [D0 + timedelta(days=60 + i) for i in range(20)]
    bars = [Bar(d, 99, 101, 98, 100 + (i % 5), 100 + (i % 5), 1000) for i, d in enumerate(days)]
    r = bt.run(bars, cfg())
    text = " ".join(r["warnings"])
    assert "gap" in text and "shorter than one year" in text
