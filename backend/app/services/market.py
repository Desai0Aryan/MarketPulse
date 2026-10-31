"""Read-side market helpers. Prices come from the repository (what the pipeline stored)."""

from __future__ import annotations

from datetime import date, timedelta

from app.ingestion.providers.base import Bar, MarketDataProvider
from app.services import container

RANGE_DAYS = {"1W": 7, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1830, "MAX": 100000}


def get_provider() -> MarketDataProvider:
    return container.get_provider()


def stored_bars(symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
    return container.get_repo().get_bars(symbol, start, end)


def window(bars: list[Bar], range_key: str) -> list[Bar]:
    if not bars or range_key == "MAX":
        return bars
    cutoff = bars[-1].day - timedelta(days=RANGE_DAYS[range_key])
    return [b for b in bars if b.day >= cutoff]


def quote(bars: list[Bar]) -> dict:
    last, prev = bars[-1], bars[-2]
    change = last.close - prev.close
    last52 = [b for b in bars if b.day >= last.day - timedelta(days=365)]
    recent = bars[-31:-1]
    avg_vol = sum(b.volume for b in recent) / max(len(recent), 1)
    return {
        "price": last.close,
        "prev_close": prev.close,
        "change": round(change, 2),
        "change_pct": round(change / prev.close * 100, 2),
        "open": last.open,
        "high": last.high,
        "low": last.low,
        "volume": last.volume,
        "avg_volume_30d": int(avg_vol),
        "rel_volume": round(last.volume / avg_vol, 2) if avg_vol else None,
        "high_52w": max(b.high for b in last52),
        "low_52w": min(b.low for b in last52),
        "as_of": last.day,
        "sparkline": [b.close for b in bars[-30:]],
    }
