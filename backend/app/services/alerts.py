"""Alert engine.

Semantics (documented in docs/api.md)
* Alerts are evaluated against STORED DAILY DATA only, one session at a time, in order. Nothing is evaluated on
  data newer than the session being examined (no look-ahead), and a session is never evaluated twice
  (`last_observed_day`), so ingestion cycles that add no new session cannot re-fire anything.
* Level kinds (price_*, change_pct_*, rsi_*, rel_volume_above) are EDGE-TRIGGERED: they fire when the condition
  turns from false to true. If the condition is already true when the alert is created (or resumed/edited) it does
  NOT fire; it waits for the condition to clear and occur again ("waiting_for_reset").
* Crossing kinds (cross_above_sma / cross_below_sma) fire on the session where the close moves from at-or-below
  to above (or at-or-above to below) the simple moving average of adjusted closes.
* `cooldown_days` additionally suppresses a fire that follows the previous fire by fewer than N calendar days.
* Every event records the stored session (`observed_day`) and the value actually observed on it. Messages only
  state what that record supports (e.g. a daily close), never an intraday price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import numpy as np

from app.analytics import indicators as ind
from app.domain import Alert, AlertEvent, utcnow
from app.ingestion.providers.base import Bar

KINDS = (
    "price_above", "price_below", "change_pct_above", "change_pct_below",
    "rsi_above", "rsi_below", "cross_above_sma", "cross_below_sma", "rel_volume_above",
)
CROSS = {"cross_above_sma", "cross_below_sma"}
LABELS = {
    "price_above": "Close above", "price_below": "Close below", "change_pct_above": "1-day change above (%)",
    "change_pct_below": "1-day change below (%)", "rsi_above": "RSI(14) above", "rsi_below": "RSI(14) below",
    "cross_above_sma": "Close crosses above SMA", "cross_below_sma": "Close crosses below SMA",
    "rel_volume_above": "Volume above multiple of 30-session average",
}
MAX_ALERTS = 50
VOL_LOOKBACK = 30


class AlertError(ValueError):
    """Invalid alert definition (HTTP 422)."""


def validate_definition(kind: str, threshold: float, window: int | None, cooldown_days: int) -> tuple[float, int | None]:
    if kind not in KINDS:
        raise AlertError(f"kind must be one of {list(KINDS)}")
    if not (0 <= cooldown_days <= 30):
        raise AlertError("cooldown_days must be between 0 and 30")
    if kind in CROSS:
        if window is None or not (5 <= window <= 250):
            raise AlertError("cross alerts need a moving-average window between 5 and 250")
        return 0.0, window
    if threshold is None or not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold):
        raise AlertError("threshold must be a finite number")
    if kind.startswith("price") and not (0 < threshold <= 10_000_000):
        raise AlertError("price threshold must be greater than 0")
    if kind.startswith("rsi") and not (0 <= threshold <= 100):
        raise AlertError("RSI threshold must be between 0 and 100")
    if kind.startswith("change_pct") and not (-100 <= threshold <= 1000):
        raise AlertError("change threshold must be between -100 and 1000 (percent)")
    if kind == "rel_volume_above" and not (0 < threshold <= 100):
        raise AlertError("volume multiple must be between 0 and 100")
    return float(threshold), None


def _series(kind: str, threshold: float, window: int | None, bars: list[Bar]) -> tuple[list[bool], list[float | None], list[float | None]]:
    """Per-session (condition, observed value, reference). Every element uses data up to that session only."""
    n = len(bars)
    close = np.array([b.close for b in bars], dtype=float)
    adj = np.array([b.adj_close for b in bars], dtype=float)
    cond, obs, ref = [False] * n, [None] * n, [None] * n
    if kind in ("price_above", "price_below"):
        for i in range(n):
            obs[i] = float(close[i])
            cond[i] = close[i] > threshold if kind == "price_above" else close[i] < threshold
    elif kind in ("change_pct_above", "change_pct_below"):
        for i in range(1, n):
            v = (close[i] / close[i - 1] - 1) * 100
            obs[i] = float(v)
            cond[i] = v > threshold if kind == "change_pct_above" else v < threshold
    elif kind in ("rsi_above", "rsi_below"):
        r = ind.rsi(adj, 14)
        for i in range(n):
            if not math.isnan(r[i]):
                obs[i] = float(r[i])
                cond[i] = r[i] > threshold if kind == "rsi_above" else r[i] < threshold
    elif kind in CROSS:
        sma = ind.sma(adj, window or 50)
        for i in range(1, n):
            if math.isnan(sma[i]) or math.isnan(sma[i - 1]):
                continue
            obs[i], ref[i] = float(adj[i]), float(sma[i])
            if kind == "cross_above_sma":
                cond[i] = bool(adj[i - 1] <= sma[i - 1] and adj[i] > sma[i])
            else:
                cond[i] = bool(adj[i - 1] >= sma[i - 1] and adj[i] < sma[i])
    elif kind == "rel_volume_above":
        vol = np.array([b.volume for b in bars], dtype=float)
        for i in range(VOL_LOOKBACK, n):
            avg = vol[i - VOL_LOOKBACK : i].mean()
            if avg > 0:
                obs[i] = float(vol[i] / avg)
                cond[i] = vol[i] / avg > threshold
    # numpy comparisons yield np.bool_; the engine's `is False` edge test and DB persistence need real bools
    return [bool(c) for c in cond], obs, ref


def _message(a: Alert, bar: Bar, value: float, ref: float | None) -> str:
    d, s = bar.day.isoformat(), a.symbol
    k = a.kind
    if k == "price_above":
        return f"{s} closed at {value:.2f} on {d}, above your {a.threshold:g} level."
    if k == "price_below":
        return f"{s} closed at {value:.2f} on {d}, below your {a.threshold:g} level."
    if k == "change_pct_above":
        return f"{s} moved {value:+.2f}% (close vs previous close) on {d}, above your {a.threshold:+g}% threshold."
    if k == "change_pct_below":
        return f"{s} moved {value:+.2f}% (close vs previous close) on {d}, below your {a.threshold:+g}% threshold."
    if k == "rsi_above":
        return f"{s} RSI(14) was {value:.1f} on {d}, above your {a.threshold:g} level."
    if k == "rsi_below":
        return f"{s} RSI(14) was {value:.1f} on {d}, below your {a.threshold:g} level."
    if k == "rel_volume_above":
        return f"{s} volume on {d} was {value:.2f}x its prior {VOL_LOOKBACK}-session average, above your {a.threshold:g}x level."
    way = "above" if k == "cross_above_sma" else "below"
    return f"{s} (adjusted close {value:.2f}) crossed {way} its {a.window}-session average ({ref:.2f}) on {d}."


@dataclass
class Evaluation:
    events: list[dict] = field(default_factory=list)
    last_observed_day: date | None = None
    last_condition: bool | None = None
    fired_in_episode: bool = False
    last_fired_day: date | None = None
    baselined: bool = False


def baseline(a: Alert, bars: list[Bar]) -> Evaluation:
    """Record the current state WITHOUT firing (used at creation, resume and edit)."""
    if not bars:
        return Evaluation()
    cond, _, _ = _series(a.kind, a.threshold, a.window, bars)
    return Evaluation(last_observed_day=bars[-1].day, last_condition=bool(cond[-1]), fired_in_episode=False,
                      last_fired_day=a.last_fired_day, baselined=True)


def evaluate(a: Alert, bars: list[Bar]) -> Evaluation:
    """Evaluate every stored session newer than `a.last_observed_day`, oldest first."""
    if not bars:
        return Evaluation(last_observed_day=a.last_observed_day, last_condition=a.last_condition,
                          fired_in_episode=a.fired_in_episode, last_fired_day=a.last_fired_day)
    if a.last_observed_day is None or a.last_condition is None:
        return baseline(a, bars)
    cond, obs, ref = _series(a.kind, a.threshold, a.window, bars)
    ev = Evaluation(last_observed_day=a.last_observed_day, last_condition=a.last_condition,
                    fired_in_episode=a.fired_in_episode, last_fired_day=a.last_fired_day)
    prev = a.last_condition
    for i, b in enumerate(bars):
        if b.day <= a.last_observed_day:
            continue
        c = cond[i]
        is_cross = a.kind in CROSS
        triggered = c and (is_cross or prev is False)
        if not c:
            ev.fired_in_episode = False
        if triggered:
            cooling = ev.last_fired_day is not None and (b.day - ev.last_fired_day).days < a.cooldown_days
            if not cooling and obs[i] is not None:
                ev.events.append({"observed_day": b.day, "observed_value": round(obs[i], 4), "message": _message(a, b, obs[i], ref[i])})
                ev.last_fired_day = b.day
                ev.fired_in_episode = True
        prev = c
        ev.last_observed_day, ev.last_condition = b.day, c
    return ev


def evaluate_all(repo, now: datetime | None = None) -> dict:
    """Evaluate every enabled alert of every owner against stored data. Safe to call after every ingestion."""
    now = now or utcnow()
    fired = checked = 0
    for a in repo.list_enabled_alerts():
        bars = repo.get_bars(a.symbol)
        ev = evaluate(a, bars)
        checked += 1
        if repo.record_evaluation(a.id, a.last_observed_day, ev, now):
            fired += len(ev.events)
    return {"alerts_checked": checked, "events_created": fired}


def new_alert(owner: str, symbol: str, kind: str, threshold: float, window: int | None, cooldown_days: int, note: str, bars: list[Bar]) -> Alert:
    thr, win = validate_definition(kind, threshold, window, cooldown_days)
    if len(bars) < 2:
        raise AlertError(f"No stored data for {symbol} yet; run an ingestion first")
    a = Alert(0, owner, symbol, kind, thr, win, cooldown_days, True, note.strip()[:200], created_day=bars[-1].day)
    b = baseline(a, bars)
    return replace(a, last_observed_day=b.last_observed_day, last_condition=b.last_condition)
