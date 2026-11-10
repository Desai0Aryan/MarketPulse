from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.deps import current_owner
from app.api.v1.stocks import _meta
from app.domain import RepoError
from app.processing.validation import normalize_symbol
from app.services import backtest as bt
from app.services import container

router = APIRouter(tags=["backtests"])
DISCLAIMER = "Historical simulation for research and education. It is not trade execution and past performance does not predict future results."


class RunBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    strategy: Literal["ma_cross", "rsi", "momentum"]
    params: dict[str, Any] = Field(default_factory=dict)
    start: date | None = None
    end: date | None = None
    initial_capital: float = 10_000
    commission_bps: float = 5
    slippage_bps: float = 5
    sizing: Literal["full", "fraction"] = "full"
    fraction: float = 1.0
    long_only: bool = True
    risk_free_pct: float = 0.0
    save: bool = True


def _http(e: Exception) -> HTTPException:
    return HTTPException(404 if e.__class__.__name__ == "NotFoundError" else 422, str(e))


@router.get("/backtests/strategies")
def strategies():
    return {"items": [{"key": k, **v} for k, v in bt.STRATEGIES.items()], "version": bt.STRATEGY_VERSION, "disclaimer": DISCLAIMER}


@router.post("/backtests")
def run_backtest(body: RunBody, owner: str = Depends(current_owner)):
    repo = container.get_repo()
    sym = normalize_symbol(body.symbol)
    if sym not in {i.symbol for i in repo.get_instruments()}:
        raise HTTPException(404, f"Unknown symbol '{body.symbol}'")
    bars = repo.get_bars(sym)
    cfg = bt.Config(sym, body.strategy, body.params, body.start, body.end, body.initial_capital, body.commission_bps, body.slippage_bps,
                    body.sizing, body.fraction, body.long_only, body.risk_free_pct)
    try:
        result = bt.run(bars, cfg, repo.get_bars("SPY"))
    except bt.BacktestError as e:
        raise HTTPException(422, str(e)) from None
    out = {"meta": _meta(), "disclaimer": DISCLAIMER, **result}
    if body.save:
        out["id"] = repo.save_backtest(owner, sym, body.strategy, result["config"], result).id
    return out


@router.get("/backtests")
def list_backtests(owner: str = Depends(current_owner)):
    return {"disclaimer": DISCLAIMER, "items": [r.summary() for r in container.get_repo().list_backtests(owner)]}


@router.get("/backtests/{run_id}")
def get_backtest(run_id: int, owner: str = Depends(current_owner)):
    try:
        r = container.get_repo().get_backtest(owner, run_id)
    except RepoError as e:
        raise _http(e) from None
    return {"meta": _meta(), "disclaimer": DISCLAIMER, "id": r.id, "created_at": r.created_at.isoformat(), **r.result}


@router.delete("/backtests/{run_id}", status_code=204)
def delete_backtest(run_id: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_backtest(owner, run_id)
    except RepoError as e:
        raise _http(e) from None
    return Response(status_code=204)
