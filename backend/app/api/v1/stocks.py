from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services import market

router = APIRouter(tags=["stocks"])


def _meta() -> dict:
    p = market.get_provider()
    return {
        "provider": p.name,
        "data_class": p.data_class,
        "demo": get_settings().is_demo,
        "notice": "Synthetic demo data. Not real market prices." if get_settings().is_demo else None,
    }


def _bars_or_404(symbol: str):
    try:
        return market.get_provider().history(symbol.upper())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{symbol.upper()}'") from None


@router.get("/stocks")
def list_stocks(kind: Literal["equity", "index_proxy", "all"] = "all"):
    provider = market.get_provider()
    items = []
    for inst in provider.instruments():
        if kind != "all" and inst.kind != kind:
            continue
        q = market.quote(provider.history(inst.symbol))
        items.append({**inst.__dict__, **q})
    return {"meta": _meta(), "items": items}


@router.get("/stocks/{symbol}")
def get_stock(symbol: str):
    bars = _bars_or_404(symbol)
    inst = next(i for i in market.get_provider().instruments() if i.symbol == symbol.upper())
    return {"meta": _meta(), "instrument": inst.__dict__, "quote": market.quote(bars)}


@router.get("/stocks/{symbol}/latest")
def latest(symbol: str):
    return {"meta": _meta(), "symbol": symbol.upper(), "quote": market.quote(_bars_or_404(symbol))}


@router.get("/stocks/{symbol}/prices")
def prices(
    symbol: str,
    range: Literal["1W", "1M", "3M", "6M", "1Y", "5Y", "MAX"] = "6M",
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(2000, ge=1, le=5000),
):
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    bars = _bars_or_404(symbol)
    if start or end:
        bars = [b for b in bars if (not start or b.day >= start) and (not end or b.day <= end)]
    else:
        bars = market.window(bars, range)
    bars = bars[-limit:]
    return {
        "meta": _meta(),
        "symbol": symbol.upper(),
        "interval": "1d",
        "price_basis": "adjusted close provided as adj_close; OHLC are unadjusted",
        "count": len(bars),
        "bars": [{**b.__dict__, "day": b.day.isoformat()} for b in bars],
    }
