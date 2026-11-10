"""Screener: per-instrument metrics + validated server-side filtering, sorting and pagination.

All metrics are computed from stored bars as of each instrument's latest session, using only data up to that
session (no look-ahead). A metric that cannot be computed (insufficient history) is `None`; a filter on a
`None` metric never matches (the instrument is excluded rather than treated as zero).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from app.analytics import indicators as ind
from app.ingestion.providers.base import Bar, Instrument

MAX_FILTERS = 12
MAX_PAGE_SIZE = 100


class ScreenError(ValueError):
    """Invalid screen definition (mapped to HTTP 422)."""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str  # "usd" | "pct" | "x" | "count" | "num" | "text" | "bool"
    description: str


NUMERIC_FIELDS: tuple[Field, ...] = (
    Field("price", "Price", "usd", "Latest close (unadjusted)"),
    Field("change_pct", "1D change %", "pct", "Close vs previous close, percent"),
    Field("volume", "Volume", "count", "Latest session volume"),
    Field("rel_volume", "Relative volume", "x", "Latest volume / mean volume of the prior 30 sessions"),
    Field("rsi14", "RSI (14)", "num", "Wilder RSI on adjusted closes, 0-100"),
    Field("volatility_20d", "Volatility (20d, ann.)", "pct", "Sample std of last 20 daily returns x sqrt(252), percent"),
    Field("dist_52w_high_pct", "Distance from 52W high %", "pct", "Close / 52-week high - 1, percent (<= 0)"),
    Field("dist_52w_low_pct", "Distance from 52W low %", "pct", "Close / 52-week low - 1, percent (>= 0)"),
    Field("price_vs_sma50_pct", "Price vs SMA50 %", "pct", "Adjusted close / SMA(50) - 1, percent"),
    Field("price_vs_sma200_pct", "Price vs SMA200 %", "pct", "Adjusted close / SMA(200) - 1, percent"),
    Field("return_1m_pct", "1M return %", "pct", "Adjusted close vs 21 sessions earlier"),
    Field("return_3m_pct", "3M return %", "pct", "Adjusted close vs 63 sessions earlier"),
)
BOOL_FIELDS: tuple[Field, ...] = (
    Field("sma50_above_sma200", "SMA50 above SMA200", "bool", "SMA(50) > SMA(200) (both must be defined)"),
)
TEXT_FIELDS = ("kind", "sector")
NUMERIC_KEYS = {f.key for f in NUMERIC_FIELDS}
BOOL_KEYS = {f.key for f in BOOL_FIELDS}
SORTABLE = NUMERIC_KEYS | {"symbol", "name"}
NUMERIC_OPS = {"gt", "gte", "lt", "lte", "between"}


def catalog() -> dict:
    return {
        "numeric": [f.__dict__ for f in NUMERIC_FIELDS],
        "boolean": [f.__dict__ for f in BOOL_FIELDS],
        "ops": sorted(NUMERIC_OPS),
        "limits": {"max_filters": MAX_FILTERS, "max_page_size": MAX_PAGE_SIZE},
    }


def _last(arr) -> float | None:
    v = float(arr[-1])
    return None if math.isnan(v) or math.isinf(v) else v


def _r(v: float | None, d: int = 4) -> float | None:
    return None if v is None else round(v, d)


def compute_metrics(inst: Instrument, bars: list[Bar]) -> dict | None:
    """Metrics for one instrument; None if there are fewer than 2 bars."""
    if len(bars) < 2:
        return None
    adj = [b.adj_close for b in bars]
    last, prev = bars[-1], bars[-2]
    year = [b for b in bars if b.day >= last.day - timedelta(days=365)]
    hi, lo = max(b.high for b in year), min(b.low for b in year)
    prior = bars[-31:-1]
    avg_vol = sum(b.volume for b in prior) / len(prior)
    rsi = _last(ind.rsi(adj, 14))
    r = ind.returns(adj)[1:]
    vol = float(r[-20:].std(ddof=1) * math.sqrt(ind.TRADING_DAYS)) if len(r) >= 20 else None
    s50, s200 = _last(ind.sma(adj, 50)), _last(ind.sma(adj, 200))

    def vs(sma: float | None) -> float | None:
        return None if sma is None else (adj[-1] / sma - 1) * 100

    def ret(n: int) -> float | None:
        return (adj[-1] / adj[-1 - n] - 1) * 100 if len(adj) > n else None

    return {
        "symbol": inst.symbol,
        "name": inst.name,
        "kind": inst.kind,
        "sector": inst.sector,
        "as_of": last.day.isoformat(),
        "price": _r(last.close, 2),
        "change_pct": _r((last.close / prev.close - 1) * 100, 2),
        "volume": last.volume,
        "rel_volume": _r(last.volume / avg_vol, 2) if avg_vol else None,
        "rsi14": _r(rsi, 2),
        "volatility_20d": _r(None if vol is None else vol * 100, 2),
        "dist_52w_high_pct": _r((last.close / hi - 1) * 100, 2),
        "dist_52w_low_pct": _r((last.close / lo - 1) * 100, 2),
        "price_vs_sma50_pct": _r(vs(s50), 2),
        "price_vs_sma200_pct": _r(vs(s200), 2),
        "return_1m_pct": _r(ret(21), 2),
        "return_3m_pct": _r(ret(63), 2),
        "sma50_above_sma200": None if s50 is None or s200 is None else s50 > s200,
    }


def validate_filters(filters: list[dict]) -> list[dict]:
    if len(filters) > MAX_FILTERS:
        raise ScreenError(f"At most {MAX_FILTERS} filters are allowed")
    out = []
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            raise ScreenError(f"filter {i + 1}: must be an object")
        field, op = f.get("field"), f.get("op")
        if field in BOOL_KEYS:
            if op != "eq" or not isinstance(f.get("value"), bool):
                raise ScreenError(f"filter {i + 1}: {field} needs op 'eq' and a true/false value")
            out.append({"field": field, "op": "eq", "value": f["value"]})
        elif field in NUMERIC_KEYS:
            if op not in NUMERIC_OPS:
                raise ScreenError(f"filter {i + 1}: op must be one of {sorted(NUMERIC_OPS)}")
            if op == "between":
                lo, hi = f.get("value"), f.get("value2")
                if not _num(lo) or not _num(hi):
                    raise ScreenError(f"filter {i + 1}: 'between' needs numeric value and value2")
                if lo > hi:
                    raise ScreenError(f"filter {i + 1}: lower bound is greater than upper bound")
                out.append({"field": field, "op": op, "value": float(lo), "value2": float(hi)})
            else:
                if not _num(f.get("value")):
                    raise ScreenError(f"filter {i + 1}: value must be a finite number")
                out.append({"field": field, "op": op, "value": float(f["value"])})
        else:
            raise ScreenError(f"filter {i + 1}: unknown field {field!r}")
    return out


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _match(row: dict, f: dict) -> bool:
    v = row.get(f["field"])
    if v is None:
        return False
    op = f["op"]
    if op == "eq":
        return v is f["value"]
    if op == "gt":
        return v > f["value"]
    if op == "gte":
        return v >= f["value"]
    if op == "lt":
        return v < f["value"]
    if op == "lte":
        return v <= f["value"]
    return f["value"] <= v <= f["value2"]


def run_screen(
    rows: list[dict],
    filters: list[dict],
    kind: str | None = None,
    sort: str = "symbol",
    descending: bool = False,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Filter -> sort -> paginate. Sort is stable; rows with a null sort value go last in either direction."""
    clean = validate_filters(filters)
    if kind not in (None, "equity", "index_proxy"):
        raise ScreenError("kind must be 'equity' or 'index_proxy'")
    if sort not in SORTABLE:
        raise ScreenError(f"sort must be one of {sorted(SORTABLE)}")
    if page < 1 or not (1 <= page_size <= MAX_PAGE_SIZE):
        raise ScreenError(f"page >= 1 and 1 <= page_size <= {MAX_PAGE_SIZE}")

    hits = [r for r in rows if (kind is None or r["kind"] == kind) and all(_match(r, f) for f in clean)]
    present = [r for r in hits if r.get(sort) is not None]
    missing = [r for r in hits if r.get(sort) is None]
    present.sort(key=lambda r: r[sort].lower() if isinstance(r[sort], str) else r[sort], reverse=descending)
    ordered = present + missing
    start = (page - 1) * page_size
    return {
        "total": len(ordered),
        "universe": len(rows),
        "page": page,
        "page_size": page_size,
        "filters": clean,
        "items": ordered[start : start + page_size],
        "all_symbols": [r["symbol"] for r in ordered],
    }


def universe_rows(repo) -> list[dict]:
    """Metrics for every instrument that has stored data (shared by the API and the research copilot)."""
    rows = []
    for inst in repo.get_instruments():
        m = compute_metrics(inst, repo.get_bars(inst.symbol))
        if m:
            rows.append(m)
    return rows
