from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.config import get_settings
from app.analytics import stats as astats
from app.services import container, export, market, technicals

router = APIRouter(tags=["stocks"])


def _meta() -> dict:
    p = market.get_provider()
    return {
        "provider": p.name,
        "data_class": p.data_class,
        "demo": get_settings().is_demo,
        "notice": "Synthetic demo data. Not real market prices." if get_settings().is_demo else None,
    }


def _instruments() -> dict:
    return {i.symbol: i for i in container.get_repo().get_instruments()}


def _bars_or_404(symbol: str):
    sym = symbol.upper()
    if sym not in _instruments():
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'")
    bars = market.stored_bars(sym)
    if len(bars) < 2:
        raise HTTPException(status_code=409, detail=f"No stored data for {sym} yet. Run an ingestion from the Data Pipeline page.")
    return bars


@router.get("/stocks")
def list_stocks(kind: Literal["equity", "index_proxy", "all"] = "all"):
    items = []
    for inst in container.get_repo().get_instruments():
        if kind != "all" and inst.kind != kind:
            continue
        bars = market.stored_bars(inst.symbol)
        if len(bars) < 2:
            continue  # not ingested yet: omit rather than fabricate
        items.append({**inst.__dict__, **market.quote(bars)})
    return {"meta": _meta(), "items": items}


@router.get("/stocks/{symbol}")
def get_stock(symbol: str):
    bars = _bars_or_404(symbol)
    inst = _instruments()[symbol.upper()]
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


@router.get("/stocks/{symbol}/indicators")
def indicators(
    symbol: str,
    range: Literal["1W", "1M", "3M", "6M", "1Y", "5Y", "MAX"] = "6M",
    limit: int = Query(2000, ge=1, le=5000),
):
    """Stored indicator values (computed by the pipeline). NULL = not enough history yet."""
    _bars_or_404(symbol)
    rows = container.get_repo().get_indicators(symbol.upper())
    if rows and range != "MAX":
        from datetime import timedelta

        cutoff = rows[-1]["day"] - timedelta(days=market.RANGE_DAYS[range])
        rows = [r for r in rows if r["day"] >= cutoff]
    rows = rows[-limit:]
    return {
        "meta": _meta(),
        "symbol": symbol.upper(),
        "price_basis": "adj_close (ATR uses unadjusted OHLC)",
        "parameters": {"sma": [20, 50, 200], "ema": [12, 26], "rsi": 14, "macd": [12, 26, 9], "bollinger": [20, 2.0], "atr": 14, "roc": 12, "vol": "20d, annualised x sqrt(252)"},
        "count": len(rows),
        "rows": [{**r, "day": r["day"].isoformat()} for r in rows],
    }


def _window_start(bars, range_key: str) -> int:
    """Index of the first bar inside the requested range."""
    w = market.window(bars, range_key)
    return len(bars) - len(w)


@router.get("/stocks/{symbol}/returns")
def returns(symbol: str, range: Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"] = "1Y"):
    bars = market.window(_bars_or_404(symbol), range)
    days, adj = [b.day for b in bars], [b.adj_close for b in bars]
    return {
        "meta": _meta(),
        "symbol": symbol.upper(),
        "range": range,
        "price_basis": "adj_close",
        "conventions": "Simple close-to-close returns; volatility annualised with 252 sessions/year; max drawdown is peak-to-trough on adjusted close.",
        "stats": astats.window_stats(days, adj),
        "series": astats.series(days, adj),
    }


@router.get("/stocks/{symbol}/technicals")
def technicals_endpoint(
    symbol: str,
    range: Literal["1W", "1M", "3M", "6M", "1Y", "5Y", "MAX"] = "6M",
    sma: str = "20,50,200",
    ema: str = "12,26",
    rsi: int = 14,
    macd: str = "12,26,9",
    bb_window: int = 20,
    bb_k: float = 2.0,
    atr: int = 14,
):
    """Indicators with user-adjustable parameters, computed from stored bars (warm-up uses full history)."""
    bars = _bars_or_404(symbol)
    try:
        macd_p = technicals.parse_int_list(macd, "macd", 2, 200, max_items=3)
        if len(macd_p) != 3:
            raise technicals.ParamError("macd needs exactly three values: fast,slow,signal")
        result = technicals.compute_technicals(
            bars,
            _window_start(bars, range),
            technicals.parse_int_list(sma, "sma", 2, 400),
            technicals.parse_int_list(ema, "ema", 2, 400),
            rsi,
            (macd_p[0], macd_p[1], macd_p[2]),
            bb_window,
            bb_k,
            atr,
        )
    except technicals.ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"meta": _meta(), "symbol": symbol.upper(), "range": range, **result}


@router.get("/stocks/{symbol}/prices.csv")
def prices_csv(symbol: str, range: Literal["1W", "1M", "3M", "6M", "1Y", "5Y", "MAX"] = "1Y"):
    bars = market.window(_bars_or_404(symbol), range)[-5000:]  # bounded export
    meta = _meta()
    body = export.build_csv(
        ["date", "open", "high", "low", "close", "adj_close", "volume"],
        [(b.day.isoformat(), b.open, b.high, b.low, b.close, b.adj_close, b.volume) for b in bars],
        {
            "MarketPulse export": "daily OHLCV",
            "symbol": symbol.upper(),
            "source": f"{meta['provider']} ({meta['data_class']})",
            "notice": meta["notice"] or "",
            "price_basis": "OHLC unadjusted; adj_close adjusted",
            "range": f"{bars[0].day} to {bars[-1].day}, {len(bars)} rows",
        },
    )
    name = export.filename(symbol.upper(), "prices", range, bars[-1].day)
    return Response(body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})
