"""Turns stored bars into indicator rows for persistence.

Price basis: return/trend indicators (SMA, EMA, RSI, MACD, Bollinger, ROC, volatility) use
`adj_close`. ATR needs a consistent high/low/close triple, so it uses the unadjusted OHLC.
Mixing is documented here and in docs/architecture.md rather than hidden.
"""

from __future__ import annotations

import math

import numpy as np

from app.analytics import indicators as ind
from app.ingestion.providers.base import Bar

INDICATOR_COLUMNS = (
    "sma20", "sma50", "sma200", "ema12", "ema26", "rsi14",
    "macd", "macd_signal", "macd_hist", "bb_lower", "bb_mid", "bb_upper",
    "atr14", "roc12", "vol20",
)


def _clean(v: float) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 6)


def compute_indicator_rows(bars: list[Bar]) -> list[dict]:
    if not bars:
        return []
    adj = np.array([b.adj_close for b in bars])
    hi = np.array([b.high for b in bars])
    lo = np.array([b.low for b in bars])
    cl = np.array([b.close for b in bars])
    macd_l, macd_s, macd_h = ind.macd(adj)
    bb_lo, bb_mid, bb_up = ind.bollinger(adj)
    cols = {
        "sma20": ind.sma(adj, 20), "sma50": ind.sma(adj, 50), "sma200": ind.sma(adj, 200),
        "ema12": ind.ema(adj, 12), "ema26": ind.ema(adj, 26), "rsi14": ind.rsi(adj, 14),
        "macd": macd_l, "macd_signal": macd_s, "macd_hist": macd_h,
        "bb_lower": bb_lo, "bb_mid": bb_mid, "bb_upper": bb_up,
        "atr14": ind.atr(hi, lo, cl, 14), "roc12": ind.roc(adj, 12), "vol20": ind.rolling_volatility(adj, 20),
    }
    return [
        {"day": b.day, **{name: _clean(cols[name][i]) for name in INDICATOR_COLUMNS}}
        for i, b in enumerate(bars)
    ]
