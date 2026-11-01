from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import current_owner
from app.domain import ConflictError, LimitError, NotFoundError, RepoError, Watchlist
from app.processing.validation import normalize_symbol
from app.services import container, market

router = APIRouter(tags=["watchlists"])


def _http(exc: RepoError) -> HTTPException:
    code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422
    return HTTPException(status_code=code, detail=str(exc))


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("name must not be blank")
    return v


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    _v = field_validator("name")(_clean_name)


class PatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    is_default: bool | None = None
    _v = field_validator("name")(lambda v: v if v is None else _clean_name(v))


class SymbolBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)


class OrderBody(BaseModel):
    symbols: list[str] = Field(max_length=100)


def _present(wl: Watchlist) -> dict:
    """Watchlist plus latest quote data per symbol (omitted, not invented, when no data is stored)."""
    items = []
    for sym in wl.symbols:
        inst = next((i for i in container.get_repo().get_instruments() if i.symbol == sym), None)
        bars = market.stored_bars(sym)
        row = {"symbol": sym, "name": inst.name if inst else sym, "exchange": inst.exchange if inst else None, "has_data": len(bars) >= 2}
        if len(bars) >= 2:
            q = market.quote(bars)
            row.update(price=q["price"], change=q["change"], change_pct=q["change_pct"], sparkline=q["sparkline"], as_of=q["as_of"])
        items.append(row)
    return {**wl.to_dict(), "items": items}


@router.get("/watchlists")
def list_watchlists(owner: str = Depends(current_owner)):
    return {"items": [_present(w) for w in container.get_repo().list_watchlists(owner)]}


@router.post("/watchlists", status_code=201)
def create_watchlist(body: NameBody, owner: str = Depends(current_owner)):
    try:
        return _present(container.get_repo().create_watchlist(owner, body.name))
    except RepoError as e:
        raise _http(e) from None


@router.patch("/watchlists/{wl_id}")
def update_watchlist(wl_id: int, body: PatchBody, owner: str = Depends(current_owner)):
    if body.is_default is False:
        raise HTTPException(status_code=422, detail="Choose another watchlist as default instead of unsetting this one")
    try:
        return _present(container.get_repo().update_watchlist(owner, wl_id, body.name, bool(body.is_default)))
    except RepoError as e:
        raise _http(e) from None


@router.delete("/watchlists/{wl_id}", status_code=204)
def delete_watchlist(wl_id: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_watchlist(owner, wl_id)
    except RepoError as e:
        raise _http(e) from None
    return Response(status_code=204)


def _sym(raw: str) -> str:
    try:
        return normalize_symbol(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid symbol") from None


@router.post("/watchlists/{wl_id}/items")
def add_item(wl_id: int, body: SymbolBody, owner: str = Depends(current_owner)):
    try:
        return _present(container.get_repo().add_watchlist_item(owner, wl_id, _sym(body.symbol)))
    except RepoError as e:
        raise _http(e) from None


@router.delete("/watchlists/{wl_id}/items/{symbol}")
def remove_item(wl_id: int, symbol: str, owner: str = Depends(current_owner)):
    try:
        return _present(container.get_repo().remove_watchlist_item(owner, wl_id, _sym(symbol)))
    except RepoError as e:
        raise _http(e) from None


@router.put("/watchlists/{wl_id}/order")
def reorder(wl_id: int, body: OrderBody, owner: str = Depends(current_owner)):
    try:
        return _present(container.get_repo().reorder_watchlist(owner, wl_id, [_sym(s) for s in body.symbols]))
    except RepoError as e:
        raise _http(e) from None
