from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import current_owner
from app.api.v1.stocks import _meta
from app.domain import ConflictError, NotFoundError, RepoError, Txn
from app.processing.validation import normalize_symbol
from app.services import container, export
from app.services import portfolio as pf


router = APIRouter(tags=["portfolio"])
DISCLAIMER = "Paper portfolio: hypothetical positions for learning. It does not represent real brokerage balances or orders."


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


def _all_bars(symbols: set[str] | None = None) -> dict[str, list]:
    repo = container.get_repo()
    return {i.symbol: repo.get_bars(i.symbol) for i in repo.get_instruments() if symbols is None or i.symbol in symbols}


def _as_of(bars: dict[str, list]) -> date:
    days = [b[-1].day for b in bars.values() if b]
    if not days:
        raise HTTPException(409, "No stored price data yet. Run an ingestion first.")
    return max(days)


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    initial_cash: Decimal = Field(Decimal(0), ge=0, le=Decimal("1000000000"))
    start_day: date | None = None

    @field_validator("name")
    @classmethod
    def _n(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v


class TxnBody(BaseModel):
    day: date
    kind: Literal["deposit", "withdraw", "buy", "sell"]
    symbol: str | None = Field(None, max_length=16)
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    amount: Decimal = Decimal(0)
    note: str = Field("", max_length=200)

    def to_txn(self) -> Txn:
        sym = normalize_symbol(self.symbol) if self.symbol else None
        return Txn(0, 0, self.day, self.kind, sym, self.quantity, self.price, self.fee, self.amount, self.note.strip())


def _summary(owner: str, pid: int, bars: dict[str, list], as_of: date) -> dict:
    txns = container.get_repo().list_txns(owner, pid)
    led = pf.replay(txns)
    prices = pf.latest_prices({s: b for s, b in bars.items() if s in led.positions}, as_of)
    return pf.value(led, prices, as_of)


@router.get("/portfolios")
def list_portfolios(owner: str = Depends(current_owner)):
    repo = container.get_repo()
    bars = _all_bars()
    as_of = _as_of(bars)
    items = []
    for p in repo.list_portfolios(owner):
        v = _summary(owner, p.id, bars, as_of)
        items.append({**p.to_dict(), "total_value": v["total_value"], "cash": v["cash"], "unrealized_pnl": v["unrealized_pnl"],
                      "realized_pnl": v["realized_pnl"], "complete": v["complete"]})
    return {"meta": _meta(), "disclaimer": DISCLAIMER, "items": items}


@router.post("/portfolios", status_code=201)
def create_portfolio(body: CreateBody, owner: str = Depends(current_owner)):
    bars = _all_bars()
    as_of = _as_of(bars)
    day = body.start_day or as_of
    if day > as_of:
        raise HTTPException(422, f"start_day {day} is after the latest data date {as_of}")
    initial = Txn(0, 0, day, "deposit", amount=body.initial_cash, note="Initial paper cash") if body.initial_cash > 0 else None
    try:
        p = container.get_repo().create_portfolio(owner, body.name, initial)
    except (RepoError, pf.PortfolioError) as e:
        raise _http(e) from None
    return p.to_dict()


@router.get("/portfolios/{pid}")
def get_portfolio(pid: int, owner: str = Depends(current_owner)):
    repo = container.get_repo()
    try:
        p = repo.get_portfolio(owner, pid)
    except RepoError as e:
        raise _http(e) from None
    bars = _all_bars()
    as_of = _as_of(bars)
    v = _summary(owner, pid, bars, as_of)
    bench = bars.get("SPY", [])
    perf = pf.performance(repo.list_txns(owner, pid), bars, bench, "SPY")
    return {"meta": _meta(), "disclaimer": DISCLAIMER, "portfolio": p.to_dict(), "summary": v, "daily_change": pf.daily_change(perf),
            "transaction_count": len(repo.list_txns(owner, pid))}


@router.delete("/portfolios/{pid}", status_code=204)
def delete_portfolio(pid: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_portfolio(owner, pid)
    except RepoError as e:
        raise _http(e) from None
    return Response(status_code=204)


@router.get("/portfolios/{pid}/transactions")
def list_txns(pid: int, owner: str = Depends(current_owner)):
    try:
        txns = container.get_repo().list_txns(owner, pid)
    except RepoError as e:
        raise _http(e) from None
    return {"items": [t.to_dict() for t in sorted(txns, key=pf.order_key, reverse=True)]}


@router.post("/portfolios/{pid}/transactions", status_code=201)
def add_txn(pid: int, body: TxnBody, owner: str = Depends(current_owner)):
    repo = container.get_repo()
    bars = _all_bars()
    as_of = _as_of(bars)
    txn = body.to_txn()
    warnings: list[str] = []
    if txn.kind in ("buy", "sell"):
        if txn.symbol not in bars or not bars[txn.symbol]:
            raise HTTPException(422, f"No stored price data for '{txn.symbol}'")
        ref = pf.latest_prices({txn.symbol: bars[txn.symbol]}, txn.day).get(txn.symbol)
        if ref is None:
            raise HTTPException(422, f"No stored price for {txn.symbol} on or before {txn.day}")
        if ref.close > 0 and abs(float(txn.price) / ref.close - 1) > 0.5:
            warnings.append(f"Price {txn.price} is more than 50% away from the stored close {ref.close:.2f} ({ref.day}); check it is intended.")
    try:
        saved = repo.add_txn(owner, pid, txn, lambda full: pf.validate_history(full, as_of))
    except (RepoError, pf.PortfolioError) as e:
        raise _http(e) from None
    return {"transaction": saved.to_dict(), "warnings": warnings}


@router.delete("/portfolios/{pid}/transactions/{tid}", status_code=204)
def delete_txn(pid: int, tid: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_txn(owner, pid, tid, pf.validate_history)  # refused if later entries depend on it
    except (RepoError, pf.PortfolioError) as e:
        raise _http(e) from None
    return Response(status_code=204)


@router.get("/portfolios/{pid}/performance")
def performance(pid: int, range: Literal["1M", "3M", "6M", "1Y", "MAX"] = "MAX", benchmark: str = Query("SPY", max_length=16),
                owner: str = Depends(current_owner)):
    repo = container.get_repo()
    try:
        txns = repo.list_txns(owner, pid)
    except RepoError as e:
        raise _http(e) from None
    bench = normalize_symbol(benchmark)
    inst = {i.symbol: i for i in repo.get_instruments()}
    if bench not in inst or inst[bench].kind != "index_proxy":
        raise HTTPException(422, "benchmark must be one of: " + ", ".join(s for s, i in inst.items() if i.kind == "index_proxy"))
    bars = _all_bars()
    as_of = _as_of(bars)
    perf = pf.performance(txns, bars, bars[bench], bench)
    if range != "MAX" and perf["days"]:
        from datetime import timedelta
        perf = pf.rebase(perf, date.fromisoformat(perf["days"][-1]) - timedelta(days={"1M": 31, "3M": 92, "6M": 183, "1Y": 366}[range]))
    return {"meta": _meta(), "disclaimer": DISCLAIMER, "range": range, "as_of": as_of.isoformat(), **perf}


@router.get("/portfolios/{pid}/transactions.csv")
def txns_csv(pid: int, owner: str = Depends(current_owner)):
    try:
        p = container.get_repo().get_portfolio(owner, pid)
        txns = sorted(container.get_repo().list_txns(owner, pid), key=pf.order_key)
    except RepoError as e:
        raise _http(e) from None
    text = export.build_csv(
        ["date", "kind", "symbol", "quantity", "price", "fee", "amount", "note"],
        [(t.day.isoformat(), t.kind, t.symbol or "", t.quantity, t.price, t.fee, t.amount, t.note) for t in txns],
        {"MarketPulse export": "paper portfolio transactions", "portfolio": p.name, "notice": DISCLAIMER},
    )
    return Response(text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="marketpulse_portfolio_transactions.csv"'})
