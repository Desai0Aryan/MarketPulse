"""Backtesting engine for simple long-only strategies. PURE: no I/O. Research/education only, not trade execution.

EXECUTION CONVENTION (the anti-look-ahead contract; tested in tests/test_backtest.py)
* A signal is computed from data up to and INCLUDING the close of day t (indicators are causal), and is acted on at
  the OPEN of the next session t+1. A signal on the final bar cannot be executed and is discarded.
* Every price used is on the ADJUSTED basis: signals use adj_close; fills use the open scaled by
  adj_close/close of the same bar (open_adj). Adjusted and raw prices are never mixed. Dividends are therefore
  implicitly reinvested; no separate dividend cash flows are modelled.
* Costs: `commission_bps` of notional per side, plus `slippage_bps` applied against us (buys fill higher, sells
  lower). Sizing: `full` = invest all cash; `fraction` = invest that fraction of equity at entry.
* Long-only. Fractional shares allowed. Cash never goes negative. Positions still open at the end are marked at the
  last close and reported as open (excluded from win rate / completed-trade count).
* The warm-up period (indicator NaNs) holds cash. Trading starts at the first session >= `start`; history before
  `start` may be used to warm indicators (past data is not look-ahead).
* Sharpe = mean(daily excess return) / std(daily return) x sqrt(252), excess = return - rf/252 (rf configurable,
  default 0%). Annualised return needs >= 252 sessions. Volatility needs >= 20 returns.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from datetime import date

import numpy as np

from app.analytics import indicators as ind
from app.ingestion.providers.base import Bar

STRATEGY_VERSION = "1.0"
STRATEGIES = {
    "ma_cross": {"label": "Moving-average crossover", "params": {"fast": 20, "slow": 50}},
    "rsi": {"label": "RSI threshold", "params": {"period": 14, "buy_below": 30, "sell_above": 55}},
    "momentum": {"label": "Momentum (lookback return)", "params": {"lookback": 60, "threshold_pct": 0.0}},
}
MIN_SESSIONS = 30


class BacktestError(ValueError):
    """Invalid backtest configuration (HTTP 422)."""


@dataclass(frozen=True)
class Config:
    symbol: str
    strategy: str
    params: dict
    start: date | None = None
    end: date | None = None
    initial_capital: float = 10_000.0
    commission_bps: float = 5.0
    slippage_bps: float = 5.0
    sizing: str = "full"  # full | fraction
    fraction: float = 1.0
    long_only: bool = True
    risk_free_pct: float = 0.0


def _num(v: object, lo: float, hi: float, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not (lo <= v <= hi):
        raise BacktestError(f"{name} must be a number between {lo:g} and {hi:g}")
    return float(v)


def _int(v: object, lo: int, hi: int, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not (lo <= v <= hi):
        raise BacktestError(f"{name} must be an integer between {lo} and {hi}")
    return int(v)


def validate(cfg: Config) -> Config:
    if cfg.strategy not in STRATEGIES:
        raise BacktestError(f"strategy must be one of {sorted(STRATEGIES)}")
    if not cfg.long_only:
        raise BacktestError("Short selling is not supported: long_only must be true")
    if cfg.sizing not in ("full", "fraction"):
        raise BacktestError("sizing must be 'full' or 'fraction'")
    _num(cfg.initial_capital, 100, 1e9, "initial_capital")
    _num(cfg.commission_bps, 0, 500, "commission_bps")
    _num(cfg.slippage_bps, 0, 500, "slippage_bps")
    _num(cfg.risk_free_pct, 0, 20, "risk_free_pct")
    if cfg.sizing == "fraction":
        _num(cfg.fraction, 0.05, 1.0, "fraction")
    if cfg.start and cfg.end and cfg.start >= cfg.end:
        raise BacktestError("start must be before end")
    p = dict(STRATEGIES[cfg.strategy]["params"]) | dict(cfg.params or {})
    unknown = set(cfg.params or {}) - set(STRATEGIES[cfg.strategy]["params"])
    if unknown:
        raise BacktestError(f"unknown parameter(s) for {cfg.strategy}: {sorted(unknown)}")
    if cfg.strategy == "ma_cross":
        f, s = _int(p["fast"], 2, 300, "fast"), _int(p["slow"], 3, 400, "slow")
        if f >= s:
            raise BacktestError("fast window must be smaller than slow window")
        p = {"fast": f, "slow": s}
    elif cfg.strategy == "rsi":
        n = _int(p["period"], 2, 100, "period")
        lo, hi = _num(p["buy_below"], 1, 99, "buy_below"), _num(p["sell_above"], 1, 99, "sell_above")
        if lo >= hi:
            raise BacktestError("buy_below must be lower than sell_above")
        p = {"period": n, "buy_below": lo, "sell_above": hi}
    else:
        p = {"lookback": _int(p["lookback"], 5, 400, "lookback"), "threshold_pct": _num(p["threshold_pct"], -50, 100, "threshold_pct")}
    return Config(**{**cfg.__dict__, "params": p})


def target_position(strategy: str, params: dict, adj: np.ndarray) -> np.ndarray:
    """Desired position (0/1) decided at the CLOSE of each day using data up to that day. NaN warm-up => 0 (flat).
    RSI is stateful (enter below `buy_below`, hold until above `sell_above`)."""
    n = len(adj)
    pos = np.zeros(n)
    if strategy == "ma_cross":
        fast, slow = ind.sma(adj, params["fast"]), ind.sma(adj, params["slow"])
        ok = ~np.isnan(fast) & ~np.isnan(slow)
        pos[ok] = (fast[ok] > slow[ok]).astype(float)
    elif strategy == "momentum":
        k = params["lookback"]
        if n > k:
            r = np.full(n, np.nan)
            r[k:] = adj[k:] / adj[:-k] - 1
            ok = ~np.isnan(r)
            pos[ok] = (r[ok] * 100 > params["threshold_pct"]).astype(float)
    else:
        r = ind.rsi(adj, params["period"])
        held = 0.0
        for i in range(n):
            if not math.isnan(r[i]):
                if held == 0 and r[i] < params["buy_below"]:
                    held = 1.0
                elif held == 1 and r[i] > params["sell_above"]:
                    held = 0.0
            pos[i] = held
    return pos


def _f(v: float | None, d: int = 6) -> float | None:
    return None if v is None or not math.isfinite(v) else round(float(v), d)


def _metrics(eq: np.ndarray, in_pos: np.ndarray, trades: list[dict], rf_pct: float) -> dict:
    n = len(eq)
    r = eq[1:] / eq[:-1] - 1 if n > 1 else np.array([])
    out: dict = {"total_return": _f(eq[-1] / eq[0] - 1), "annualized_return": None, "annualized_volatility": None, "sharpe": None,
                 "max_drawdown": _f(ind.max_drawdown(eq)), "exposure": _f(float(in_pos.mean())), "completed_trades": len(trades),
                 "win_rate": _f(sum(1 for t in trades if t["pnl"] > 0) / len(trades)) if trades else None, "notes": []}
    if n >= 252:
        out["annualized_return"] = _f((eq[-1] / eq[0]) ** (252 / (n - 1)) - 1)
    else:
        out["notes"].append("Annualised return needs at least 252 sessions.")
    if len(r) >= 20:
        sd = float(np.std(r, ddof=1))
        out["annualized_volatility"] = _f(sd * math.sqrt(252))
        if sd > 0:
            out["sharpe"] = _f((float(np.mean(r)) - rf_pct / 100 / 252) / sd * math.sqrt(252), 4)
    else:
        out["notes"].append("Volatility and Sharpe need at least 20 daily returns.")
    if not trades:
        out["notes"].append("No completed trades in this period.")
    return out


def run(bars: list[Bar], cfg: Config, benchmark: list[Bar] | None = None) -> dict:
    t0 = time.perf_counter()
    cfg = validate(cfg)
    if len(bars) < 2:
        raise BacktestError("No stored data for this symbol")
    adj = np.array([b.adj_close for b in bars], dtype=float)
    open_adj = np.array([b.open * (b.adj_close / b.close) for b in bars], dtype=float)  # same basis as signals
    days = [b.day for b in bars]
    sig = target_position(cfg.strategy, cfg.params, adj)

    i0 = next((i for i, d in enumerate(days) if cfg.start is None or d >= cfg.start), None)
    i1 = max((i for i, d in enumerate(days) if cfg.end is None or d <= cfg.end), default=None)
    if i0 is None or i1 is None or i1 - i0 + 1 < MIN_SESSIONS:
        raise BacktestError(f"Need at least {MIN_SESSIONS} stored sessions inside the selected range")

    cost = cfg.commission_bps / 1e4
    slip = cfg.slippage_bps / 1e4
    cash, qty = cfg.initial_capital, 0.0
    entry: dict | None = None
    trades: list[dict] = []
    equity, in_pos, markers = [], [], []
    for i in range(i0, i1 + 1):
        # 1) execute the decision made at the previous close, at TODAY'S OPEN
        if i > i0:
            want = sig[i - 1]
            if want > 0 and qty == 0:
                fill = open_adj[i] * (1 + slip)
                budget = cash if cfg.sizing == "full" else min(cash, cfg.fraction * (cash + qty * open_adj[i]))
                q = budget / (fill * (1 + cost))
                if q > 0:
                    spend = q * fill * (1 + cost)
                    cash -= spend
                    qty = q
                    entry = {"entry_day": days[i].isoformat(), "entry_price": fill, "qty": q, "entry_cost": q * fill * cost, "cash_out": spend, "i": i}
                    markers.append({"day": days[i].isoformat(), "side": "buy", "price": _f(fill, 4)})
            elif want == 0 and qty > 0 and entry:
                fill = open_adj[i] * (1 - slip)
                proceeds = qty * fill * (1 - cost)
                cash += proceeds
                pnl = proceeds - entry["cash_out"]
                trades.append({"entry_day": entry["entry_day"], "entry_price": _f(entry["entry_price"], 4), "exit_day": days[i].isoformat(),
                               "exit_price": _f(fill, 4), "qty": _f(qty, 6), "pnl": _f(pnl, 2), "return_pct": _f(pnl / entry["cash_out"] * 100, 3),
                               "costs": _f(entry["entry_cost"] + qty * fill * cost, 2), "bars_held": i - entry["i"], "open": False})
                markers.append({"day": days[i].isoformat(), "side": "sell", "price": _f(fill, 4)})
                qty, entry = 0.0, None
        # 2) mark to market at today's close
        equity.append(cash + qty * adj[i])
        in_pos.append(1.0 if qty > 0 else 0.0)

    open_trade = None
    if qty > 0 and entry:
        mv = qty * adj[i1]
        open_trade = {"entry_day": entry["entry_day"], "entry_price": _f(entry["entry_price"], 4), "exit_day": None, "exit_price": _f(adj[i1], 4),
                      "qty": _f(qty, 6), "pnl": _f(mv - entry["cash_out"], 2), "return_pct": _f((mv / entry["cash_out"] - 1) * 100, 3),
                      "costs": _f(entry["entry_cost"], 2), "bars_held": i1 - entry["i"], "open": True}

    eq = np.array(equity)
    run_days = [d.isoformat() for d in days[i0 : i1 + 1]]
    # buy & hold on the SAME basis, with the same costs: buy at the open of the second session.
    j = i0 + 1
    bh_fill = open_adj[j] * (1 + slip)
    bh_qty = cfg.initial_capital / (bh_fill * (1 + cost))
    bh = np.array([cfg.initial_capital if k <= i0 else bh_qty * adj[k] for k in range(i0, i1 + 1)])
    result = {
        "equity": [_f(v, 2) for v in eq],
        "buy_hold": [_f(v, 2) for v in bh],
        "drawdown": [_f(v) for v in ind.drawdown_series(eq)],
        "days": run_days,
        "markers": markers,
        "trades": trades + ([open_trade] if open_trade else []),
        "metrics": _metrics(eq, np.array(in_pos), trades, cfg.risk_free_pct),
        "buy_hold_metrics": {"total_return": _f(bh[-1] / bh[0] - 1), "max_drawdown": _f(ind.max_drawdown(bh))},
        "final_equity": _f(eq[-1], 2),
    }
    if benchmark:
        bmap = {b.day.isoformat(): b.adj_close for b in benchmark}
        vals = [bmap.get(d) for d in run_days]
        if vals[0] is not None and vals[-1] is not None:
            result["benchmark_return"] = _f(vals[-1] / vals[0] - 1)
    warnings = []
    gaps = [(days[k], days[k - 1]) for k in range(i0 + 1, i1 + 1) if (days[k] - days[k - 1]).days > 5]
    if gaps:
        warnings.append(f"{len(gaps)} gap(s) longer than 5 calendar days in the stored data (first: {gaps[0][1]} to {gaps[0][0]}); trades across gaps use the next stored open.")
    if i1 - i0 + 1 < 252:
        warnings.append("Sample shorter than one year: treat results as anecdotal.")
    if not np.any(np.array(in_pos) > 0):
        warnings.append("The strategy never entered a position in this window (warm-up or no signal).")
    result["warnings"] = warnings
    result["config"] = {
        "symbol": cfg.symbol, "strategy": cfg.strategy, "strategy_version": STRATEGY_VERSION, "params": cfg.params,
        "start": run_days[0], "end": run_days[-1], "initial_capital": cfg.initial_capital, "commission_bps": cfg.commission_bps,
        "slippage_bps": cfg.slippage_bps, "sizing": cfg.sizing, "fraction": cfg.fraction, "long_only": True, "risk_free_pct": cfg.risk_free_pct,
    }
    result["reproducibility"] = {
        "strategy_version": STRATEGY_VERSION, "sessions": len(run_days), "data_range": [days[0].isoformat(), days[-1].isoformat()],
        "data_fingerprint": hashlib.sha256(",".join(f"{b.day}:{b.adj_close:.6f}:{b.open:.6f}" for b in bars[: i1 + 1]).encode()).hexdigest()[:16],
        "assumptions": [
            "Signals use data through the close of day t; fills occur at the open of day t+1.",
            "Adjusted prices throughout (signals on adj_close, fills on the adjusted open); dividends implicitly reinvested.",
            f"Costs: {cfg.commission_bps:g} bps commission per side, {cfg.slippage_bps:g} bps adverse slippage.",
            "Long-only, fractional shares, no leverage; open positions are marked at the last close.",
            f"Sharpe uses a {cfg.risk_free_pct:g}% annual risk-free rate and 252 sessions per year.",
        ],
    }
    result["execution_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result
