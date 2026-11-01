"""Return / risk statistics over a price window (adj_close basis)."""

from __future__ import annotations

import math

import numpy as np

from app.analytics import indicators as ind

MIN_SESSIONS_FOR_ANNUALISED_RETURN = 252


def _f(v: float) -> float | None:
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), 6)


def window_stats(days: list, adj: list[float]) -> dict:
    """Total/annualised return, annualised volatility, max drawdown, best/worst day.

    * Daily returns are simple close-to-close; the first observation has no return (never zero-filled).
    * Annualised volatility = sample std (ddof=1) of daily returns x sqrt(252); needs >= 20 returns.
    * Annualised return (CAGR-style, 252 sessions/year) is reported only with >= 252 sessions,
      because compounding a short window to a year is misleading.
    """
    x = np.asarray(adj, dtype=float)
    n = len(x)
    out: dict = {"sessions": n, "total_return": None, "annualized_return": None, "annualized_volatility": None,
                 "max_drawdown": None, "best_day": None, "worst_day": None, "notes": []}
    if n < 2:
        out["notes"].append("Not enough data (need at least 2 sessions).")
        return out
    r = ind.returns(x)[1:]
    out["total_return"] = _f(x[-1] / x[0] - 1)
    out["max_drawdown"] = _f(ind.max_drawdown(x))
    i_best, i_worst = int(np.argmax(r)), int(np.argmin(r))
    out["best_day"] = {"day": str(days[i_best + 1]), "return": _f(r[i_best])}
    out["worst_day"] = {"day": str(days[i_worst + 1]), "return": _f(r[i_worst])}
    if len(r) >= 20:
        out["annualized_volatility"] = _f(np.std(r, ddof=1) * math.sqrt(ind.TRADING_DAYS))
    else:
        out["notes"].append("Volatility needs at least 20 daily returns.")
    if n >= MIN_SESSIONS_FOR_ANNUALISED_RETURN:
        out["annualized_return"] = _f((x[-1] / x[0]) ** (ind.TRADING_DAYS / (n - 1)) - 1)
    else:
        out["notes"].append("Annualised return needs at least 252 sessions; shown as unavailable for shorter windows.")
    return out


def series(days: list, adj: list[float]) -> dict:
    x = np.asarray(adj, dtype=float)
    r = ind.returns(x)
    return {
        "days": [str(d) for d in days],
        "daily_return": [_f(v) for v in r],  # first is null
        "cumulative_return": [_f(v) for v in ind.cumulative_returns(x)],
        "drawdown": [_f(v) for v in ind.drawdown_series(x)],
    }
