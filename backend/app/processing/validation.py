"""Normalisation and validation of provider records.

Nothing is silently dropped: every rejected record is returned with a machine-readable code,
and suspicious-but-kept records are returned as warnings.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.domain import Rejection
from app.ingestion.providers.base import Bar

# Provider-specific field names -> canonical names.
FIELD_ALIASES = {
    "day": ("day", "date", "timestamp", "t", "datetime"),
    "open": ("open", "o", "1. open"),
    "high": ("high", "h", "2. high"),
    "low": ("low", "l", "3. low"),
    "close": ("close", "c", "4. close"),
    "adj_close": ("adj_close", "adjclose", "adjusted_close", "adj close", "5. adjusted close"),
    "volume": ("volume", "v", "5. volume", "6. volume"),
}


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s or len(s) > 12 or not all(c.isalnum() or c in ".-" for c in s):
        raise ValueError(f"invalid symbol: {symbol!r}")
    return s


def _pick(raw: Mapping[str, Any], name: str) -> Any:
    lower = {str(k).lower(): v for k, v in raw.items()}
    for alias in FIELD_ALIASES[name]:
        if alias in lower and lower[alias] is not None:
            return lower[alias]
    return None


def _to_day(v: Any) -> date:
    if isinstance(v, datetime):
        return (v.astimezone(UTC) if v.tzinfo else v).date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):  # epoch seconds (UTC)
        return datetime.fromtimestamp(float(v), UTC).date()
    return date.fromisoformat(str(v)[:10])


def normalize_bar(raw: Mapping[str, Any]) -> Bar:
    """Map a provider dict to a canonical Bar. Raises ValueError("missing_field:<name>") or
    ValueError("bad_value:<name>") so the caller can record a precise rejection."""
    got: dict[str, Any] = {}
    for name in FIELD_ALIASES:
        got[name] = _pick(raw, name)
    for required in ("day", "open", "high", "low", "close", "volume"):
        if got[required] is None:
            raise ValueError(f"missing_field:{required}")
    try:
        day = _to_day(got["day"])
        o, h, l, c = (float(got[k]) for k in ("open", "high", "low", "close"))
        adj = float(got["adj_close"]) if got["adj_close"] is not None else c
        vol = int(float(got["volume"]))
    except (ValueError, TypeError) as exc:
        raise ValueError("bad_value:unparseable") from exc
    return Bar(day=day, open=o, high=h, low=l, close=c, adj_close=adj, volume=vol)


@dataclass
class ValidationResult:
    accepted: list[Bar] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)  # severity="error"
    warnings: list[Rejection] = field(default_factory=list)  # accepted, but suspicious

    @property
    def all_flags(self) -> list[Rejection]:
        return [*self.rejected, *self.warnings]


def validate_bars(
    symbol: str,
    bars: Iterable[Bar],
    prev_close: float | None = None,
    max_jump: float = 0.40,
) -> ValidationResult:
    """Validate a batch ordered as delivered by the provider.

    Errors (rejected): non-finite or non-positive prices, high < low, OHLC bounds violated,
    negative volume, non-positive adj_close, duplicate day within the batch, out-of-order day.
    Warnings (kept): close-to-close move larger than `max_jump` vs the previous accepted close,
    adj_close above close (an adjusted series should not exceed the raw one).
    """
    res = ValidationResult()
    last_day: date | None = None
    seen: set[date] = set()
    prev = prev_close

    def err(b: Bar, code: str, detail: str) -> None:
        res.rejected.append(Rejection(symbol, b.day, code, "error", detail, _raw(b)))

    for b in bars:
        nums = (b.open, b.high, b.low, b.close, b.adj_close)
        if any(not math.isfinite(v) for v in nums):
            err(b, "non_finite_price", "price field is NaN or infinite")
            continue
        if any(v <= 0 for v in nums):
            err(b, "nonpositive_price", "price fields must be > 0")
            continue
        if b.volume < 0:
            err(b, "negative_volume", f"volume={b.volume}")
            continue
        if b.high < b.low or b.high < max(b.open, b.close) or b.low > min(b.open, b.close):
            err(b, "invalid_ohlc", f"o={b.open} h={b.high} l={b.low} c={b.close}")
            continue
        if b.day in seen:
            err(b, "duplicate_timestamp", f"{b.day} appears more than once in the batch")
            continue
        if last_day is not None and b.day < last_day:
            err(b, "out_of_order", f"{b.day} arrived after {last_day}")
            continue
        seen.add(b.day)
        last_day = b.day
        if prev is not None and abs(b.close / prev - 1) > max_jump:
            res.warnings.append(
                Rejection(symbol, b.day, "unexpected_jump", "warning", f"close moved {b.close / prev - 1:+.1%} vs previous close", _raw(b))
            )
        if b.adj_close > b.close * 1.001:
            res.warnings.append(
                Rejection(symbol, b.day, "inconsistent_adjusted_price", "warning", f"adj_close {b.adj_close} > close {b.close}", _raw(b))
            )
        res.accepted.append(b)
        prev = b.close
    return res


def _raw(b: Bar) -> dict:
    return {"day": b.day.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "adj_close": b.adj_close, "volume": b.volume}
