"""Vectorised technical indicators.

Conventions (apply to every function):
* Inputs are 1-D float arrays ordered oldest -> newest.
* Output has the same length. Positions where the indicator is not yet defined
  (insufficient history) are NaN. Missing data is never replaced by zero.
* Every value at index t uses only observations at indices <= t (no look-ahead).
* Initialisation rules are stated per function.
* Annualisation uses 252 sessions per year. That is a US-equity convention; it
  ignores holidays/half-days and assumes returns are roughly i.i.d., so annualised
  volatility is an estimate, not a guarantee.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def sma(x, window: int) -> np.ndarray:
    """Simple moving average: mean of the last `window` values. First defined at index window-1."""
    x = _arr(x)
    out = np.full(len(x), np.nan)
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return out
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[window - 1 :] = (c[window:] - c[:-window]) / window
    return out


def ema(x, span: int) -> np.ndarray:
    """Exponential moving average, alpha = 2/(span+1).

    Seeded with the SMA of the first `span` values (first defined at index span-1), then
    EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}. NaNs before the seed are preserved.
    """
    x = _arr(x)
    out = np.full(len(x), np.nan)
    if span < 1:
        raise ValueError("span must be >= 1")
    if len(x) < span:
        return out
    alpha = 2.0 / (span + 1)
    out[span - 1] = x[:span].mean()
    for i in range(span, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _wilder(x: np.ndarray, period: int, start: int) -> np.ndarray:
    """Wilder smoothing seeded at index `start` with the mean of x[start-period+1 : start+1]."""
    out = np.full(len(x), np.nan)
    if len(x) <= start:
        return out
    out[start] = x[start - period + 1 : start + 1].mean()
    for i in range(start + 1, len(x)):
        out[i] = (out[i - 1] * (period - 1) + x[i]) / period
    return out


def rsi(x, period: int = 14) -> np.ndarray:
    """Wilder's RSI. Average gain/loss are seeded with the simple mean of the first `period`
    changes, so the first value appears at index `period`. RSI = 100 - 100/(1+RS);
    if average loss is 0 the value is 100 (and 50 when there is also no gain)."""
    x = _arr(x)
    out = np.full(len(x), np.nan)
    if len(x) <= period:
        return out
    delta = np.diff(x, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain[0] = loss[0] = 0.0
    ag = _wilder(gain, period, period)
    al = _wilder(loss, period, period)
    valid = ~np.isnan(ag)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = ag[valid] / al[valid]
        vals = 100 - 100 / (1 + rs)
    vals = np.where(al[valid] == 0, np.where(ag[valid] == 0, 50.0, 100.0), vals)
    out[valid] = vals
    return out


def macd(x, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD line = EMA(fast) - EMA(slow); signal = EMA(signal) of the MACD line (seeded with the
    SMA of its first `signal` defined values); histogram = macd - signal."""
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")
    x = _arr(x)
    line = ema(x, fast) - ema(x, slow)
    sig = np.full(len(x), np.nan)
    first = int(np.argmax(~np.isnan(line))) if (~np.isnan(line)).any() else None
    if first is not None and len(x) >= first + signal:
        sig[first + signal - 1] = line[first : first + signal].mean()
        alpha = 2.0 / (signal + 1)
        for i in range(first + signal, len(x)):
            sig[i] = alpha * line[i] + (1 - alpha) * sig[i - 1]
    return line, sig, line - sig


def bollinger(x, window: int = 20, k: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: middle = SMA(window); bands = middle ± k * population std (ddof=0)
    over the same window."""
    x = _arr(x)
    mid = sma(x, window)
    sq = sma(x**2, window)
    std = np.sqrt(np.maximum(sq - mid**2, 0.0))
    return mid - k * std, mid, mid + k * std


def atr(high, low, close, period: int = 14) -> np.ndarray:
    """Average True Range with Wilder smoothing. TR_0 = high-low; TR_t = max(h-l, |h-c_{t-1}|,
    |l-c_{t-1}|). Seeded with the mean of the first `period` TRs (first value at index period-1)."""
    h, l, c = _arr(high), _arr(low), _arr(close)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    tr[0] = h[0] - l[0]
    if len(tr) < period:
        return np.full(len(tr), np.nan)
    return _wilder(tr, period, period - 1)


def roc(x, period: int = 12) -> np.ndarray:
    """Rate of change in percent: (x_t / x_{t-period} - 1) * 100."""
    x = _arr(x)
    out = np.full(len(x), np.nan)
    if len(x) > period:
        out[period:] = (x[period:] / x[:-period] - 1) * 100
    return out


def returns(x) -> np.ndarray:
    """Simple daily returns x_t/x_{t-1} - 1. Index 0 is NaN (no prior observation)."""
    x = _arr(x)
    out = np.full(len(x), np.nan)
    if len(x) > 1:
        out[1:] = x[1:] / x[:-1] - 1
    return out


def cumulative_returns(x) -> np.ndarray:
    """Return since the first observation: x_t / x_0 - 1."""
    x = _arr(x)
    return x / x[0] - 1 if len(x) else x


def rolling_volatility(x, window: int = 20, annualize: bool = True) -> np.ndarray:
    """Rolling sample std (ddof=1) of simple returns over `window` returns, optionally x sqrt(252).
    First defined at index `window`."""
    r = returns(x)
    out = np.full(len(r), np.nan)
    if len(r) <= window:
        return out
    for i in range(window, len(r)):
        out[i] = np.std(r[i - window + 1 : i + 1], ddof=1)
    return out * np.sqrt(TRADING_DAYS) if annualize else out


def max_drawdown(x) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.35). 0.0 if never below peak."""
    x = _arr(x)
    if len(x) == 0:
        return float("nan")
    peak = np.maximum.accumulate(x)
    return float((x / peak - 1).min())


def drawdown_series(x) -> np.ndarray:
    x = _arr(x)
    return x / np.maximum.accumulate(x) - 1
