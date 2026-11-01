"""Parameterised indicator computation for the stock terminal.

Indicators are computed over the FULL stored history so warm-up periods are correct, then the response is
cut to the requested window. Parameters are validated and bounded (the UI lets users change them).
"""

from __future__ import annotations

from app.analytics import indicators as ind
from app.ingestion.providers.base import Bar


class ParamError(ValueError):
    pass


def parse_int_list(raw: str, name: str, lo: int, hi: int, max_items: int = 4) -> list[int]:
    try:
        vals = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ParamError(f"{name} must be a comma-separated list of integers") from None
    if len(vals) > max_items:
        raise ParamError(f"{name}: at most {max_items} values")
    if any(v < lo or v > hi for v in vals):
        raise ParamError(f"{name}: each value must be between {lo} and {hi}")
    return list(dict.fromkeys(vals))


def _clean(arr) -> list[float | None]:
    return [None if v != v else round(float(v), 4) for v in arr]  # NaN != NaN


def compute_technicals(
    bars: list[Bar],
    window_start: int,
    sma: list[int],
    ema: list[int],
    rsi_period: int,
    macd_params: tuple[int, int, int],
    bb_window: int,
    bb_k: float,
    atr_period: int,
) -> dict:
    if not (2 <= rsi_period <= 100):
        raise ParamError("rsi must be between 2 and 100")
    fast, slow, sig = macd_params
    if not (2 <= fast < slow <= 200) or not (2 <= sig <= 100):
        raise ParamError("macd needs 2 <= fast < slow <= 200 and 2 <= signal <= 100")
    if not (5 <= bb_window <= 200) or not (0.5 <= bb_k <= 4.0):
        raise ParamError("bollinger needs window 5-200 and k 0.5-4")
    if not (2 <= atr_period <= 100):
        raise ParamError("atr must be between 2 and 100")

    adj = [b.adj_close for b in bars]
    sl = slice(window_start, None)
    line, signal, hist = ind.macd(adj, fast, slow, sig)
    lo, mid, up = ind.bollinger(adj, bb_window, bb_k)
    atr = ind.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars], atr_period)
    return {
        "days": [b.day.isoformat() for b in bars[sl]],
        "parameters": {"sma": sma, "ema": ema, "rsi": rsi_period, "macd": [fast, slow, sig], "bollinger": [bb_window, bb_k], "atr": atr_period},
        "sma": {str(w): _clean(ind.sma(adj, w)[sl]) for w in sma},
        "ema": {str(w): _clean(ind.ema(adj, w)[sl]) for w in ema},
        "rsi": _clean(ind.rsi(adj, rsi_period)[sl]),
        "macd": {"line": _clean(line[sl]), "signal": _clean(signal[sl]), "hist": _clean(hist[sl])},
        "bollinger": {"lower": _clean(lo[sl]), "mid": _clean(mid[sl]), "upper": _clean(up[sl])},
        "atr": _clean(atr[sl]),
        "formulas": {
            "sma": "SMA(n) = mean of the last n adjusted closes",
            "ema": "EMA(n): alpha = 2/(n+1); seeded with SMA(n); EMA_t = alpha*x_t + (1-alpha)*EMA_{t-1}",
            "rsi": "Wilder RSI: RS = avg gain / avg loss (Wilder smoothing, seeded with the simple mean); RSI = 100 - 100/(1+RS)",
            "macd": "MACD = EMA(fast) - EMA(slow); signal = EMA(signal) of MACD; histogram = MACD - signal",
            "bollinger": "middle = SMA(n); bands = middle ± k × population std over n closes",
            "atr": "ATR: Wilder-smoothed true range = max(H-L, |H-C_prev|, |L-C_prev|); unadjusted OHLC",
        },
        "disclaimer": "Indicators describe past prices. They are not buy or sell signals and do not predict future returns.",
        "price_basis": "adj_close (ATR uses unadjusted OHLC)",
    }
