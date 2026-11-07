"""Comparison workspace: aligned performance, risk stats, correlation matrix and rolling correlation.

Alignment: series are inner-joined on trading days (only days present for EVERY selected symbol are used), so
no value is forward-filled or invented. Coverage per symbol and the number of dropped days are reported.
All returns use adjusted closes.
"""

from __future__ import annotations

import math

import numpy as np

from app.analytics import indicators as ind
from app.analytics import stats as astats
from app.ingestion.providers.base import Bar

MIN_SYMBOLS, MAX_SYMBOLS = 2, 10
MIN_COMMON_SESSIONS = 30
MIN_ROLLING, MAX_ROLLING = 10, 250


class CompareError(ValueError):
    """Invalid comparison request (HTTP 422)."""


def _f(v: float) -> float | None:
    return None if v is None or math.isnan(v) or math.isinf(v) else round(float(v), 6)


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation; NaN when either series is constant or there are < 3 points."""
    if len(a) < 3:
        return float("nan")
    sa, sb = a.std(), b.std()
    if sa == 0 or sb == 0:
        return float("nan")
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def rolling_correlation(a: np.ndarray, b: np.ndarray, window: int) -> np.ndarray:
    """Correlation over the trailing `window` observations; NaN until `window` points exist."""
    out = np.full(len(a), np.nan)
    for i in range(window - 1, len(a)):
        out[i] = pearson(a[i - window + 1 : i + 1], b[i - window + 1 : i + 1])
    return out


def align(series: dict[str, list[Bar]]) -> tuple[list, dict[str, np.ndarray], dict[str, dict]]:
    common = set.intersection(*(set(b.day for b in bars) for bars in series.values()))
    days = sorted(common)
    values = {s: np.array(_adj_on(bars, common), dtype=float) for s, bars in series.items()}
    coverage = {s: {"sessions": len(bars), "dropped": len(bars) - len(days)} for s, bars in series.items()}
    return days, values, coverage


def _adj_on(bars: list[Bar], common: set) -> list[float]:
    return [b.adj_close for b in bars if b.day in common]  # bars are day-ascending


def compare(series: dict[str, list[Bar]], rolling_pair: tuple[str, str] | None = None, rolling_window: int = 60) -> dict:
    n = len(series)
    if not (MIN_SYMBOLS <= n <= MAX_SYMBOLS):
        raise CompareError(f"Choose between {MIN_SYMBOLS} and {MAX_SYMBOLS} distinct symbols")
    if not (MIN_ROLLING <= rolling_window <= MAX_ROLLING):
        raise CompareError(f"rolling window must be between {MIN_ROLLING} and {MAX_ROLLING}")
    syms = list(series)
    if rolling_pair is not None and (rolling_pair[0] == rolling_pair[1] or not set(rolling_pair) <= set(syms)):
        raise CompareError("rolling pair must be two different selected symbols")
    days, values, coverage = align(series)
    if len(days) < MIN_COMMON_SESSIONS:
        raise CompareError(f"Only {len(days)} common trading sessions; need at least {MIN_COMMON_SESSIONS}")

    rets = {s: ind.returns(v)[1:] for s, v in values.items()}
    matrix = [[1.0 if a == b else _f(pearson(rets[a], rets[b])) for b in syms] for a in syms]
    notes: list[str] = []
    if any(c["dropped"] for c in coverage.values()):
        notes.append("Only sessions present for every selected symbol are used; unmatched days were dropped, not filled.")
    if any(v is None for row in matrix for v in row):
        notes.append("Some correlations are unavailable (constant series or too few points).")

    result = {
        "days": [d.isoformat() for d in days],
        "symbols": syms,
        "normalized": {s: [_f(x) for x in v / v[0] * 100] for s, v in values.items()},
        "stats": {s: astats.window_stats(days, list(v)) for s, v in values.items()},
        "correlation": {"symbols": syms, "matrix": matrix, "basis": "Pearson, daily simple returns over the aligned window"},
        "coverage": coverage,
        "notes": notes,
        "basis": "Adjusted closes, rebased to 100 on the first common session.",
    }
    if rolling_pair:
        a, b = rolling_pair
        rc = rolling_correlation(rets[a], rets[b], rolling_window)
        result["rolling_correlation"] = {
            "pair": [a, b],
            "window": rolling_window,
            "days": [d.isoformat() for d in days[1:]],
            "values": [_f(x) for x in rc],
        }
    return result
