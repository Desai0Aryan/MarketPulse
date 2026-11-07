from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.v1.stocks import _meta
from app.processing.validation import normalize_symbol
from app.services import compare as cmp
from app.services import container, export, market

router = APIRouter(tags=["compare"])
RangeKey = Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"]


class CompareBody(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=cmp.MAX_SYMBOLS)
    range: RangeKey = "1Y"
    rolling_pair: list[str] | None = Field(None, min_length=2, max_length=2)
    rolling_window: int = Field(60, ge=cmp.MIN_ROLLING, le=cmp.MAX_ROLLING)


def _run(body: CompareBody) -> dict:
    known = {i.symbol for i in container.get_repo().get_instruments()}
    syms: list[str] = []
    for raw in body.symbols:
        s = normalize_symbol(raw)
        if s not in known:
            raise HTTPException(status_code=404, detail=f"Unknown symbol '{raw}'")
        if s not in syms:
            syms.append(s)
    series = {}
    for s in syms:
        bars = market.stored_bars(s)
        if len(bars) < 2:
            raise HTTPException(status_code=409, detail=f"No stored data for {s} yet")
        series[s] = market.window(bars, body.range)
    pair = None
    if body.rolling_pair:
        pair = (normalize_symbol(body.rolling_pair[0]), normalize_symbol(body.rolling_pair[1]))
    try:
        return cmp.compare(series, pair, body.rolling_window)
    except cmp.CompareError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/compare")
def compare(body: CompareBody):
    return {"meta": _meta(), "range": body.range, **_run(body)}


@router.post("/compare/export.csv")
def compare_csv(body: CompareBody):
    res = _run(body)
    meta = _meta()
    syms = res["symbols"]
    text = export.build_csv(
        ["date", *[f"{s}_rebased_100" for s in syms]],
        [[d, *[res["normalized"][s][i] for s in syms]] for i, d in enumerate(res["days"])],
        {
            "MarketPulse export": "comparison (rebased to 100)",
            "symbols": ",".join(syms),
            "source": f"{meta['provider']} ({meta['data_class']})",
            "notice": meta["notice"] or "",
            "basis": res["basis"],
            "range": f"{res['days'][0]} to {res['days'][-1]}, {len(res['days'])} common sessions",
        },
    )
    name = export.filename("-".join(syms)[:60], "compare", body.range, date.fromisoformat(res["days"][-1]))
    return Response(text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})
