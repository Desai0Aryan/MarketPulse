from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import current_owner
from app.api.v1.stocks import _meta
from app.domain import ConflictError, LimitError, NotFoundError, RepoError
from app.services import container, export, market, screener

router = APIRouter(tags=["screener"])


class ScreenBody(BaseModel):
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=screener.MAX_FILTERS)
    kind: Literal["equity", "index_proxy"] | None = None
    sort: str = "symbol"
    descending: bool = False
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=screener.MAX_PAGE_SIZE)


class SaveBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    definition: ScreenBody

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v


def _rows() -> list[dict]:
    return screener.universe_rows(container.get_repo())


def _run(body: ScreenBody, **override) -> dict:
    args = {**body.model_dump(), **override}
    try:
        return screener.run_screen(_rows(), args["filters"], args["kind"], args["sort"], args["descending"], args["page"], args["page_size"])
    except screener.ScreenError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/screener/fields")
def fields():
    return screener.catalog()


@router.post("/screener/query")
def query(body: ScreenBody):
    res = _run(body)
    return {"meta": _meta(), **res}


@router.post("/screener/export.csv")
def export_csv(body: ScreenBody):
    res = _run(body, page=1, page_size=screener.MAX_PAGE_SIZE)
    meta = _meta()
    cols = ["symbol", "name", "kind", "sector"] + [f.key for f in screener.NUMERIC_FIELDS] + ["sma50_above_sma200"]
    rows = [[r.get(c) for c in cols] for r in res["items"]]
    desc = "; ".join(
        f"{f['field']} {f['op']} {f['value']}" + (f"..{f['value2']}" if "value2" in f else "") for f in res["filters"]
    ) or "no filters"
    text = export.build_csv(
        cols,
        rows,
        {
            "MarketPulse export": "screener results",
            "source": f"{meta['provider']} ({meta['data_class']})",
            "notice": meta["notice"] or "",
            "filters": desc,
            "rows": f"{len(rows)} of {res['total']} matches (export capped at {screener.MAX_PAGE_SIZE})",
            "as_of": res["items"][0]["as_of"] if res["items"] else "",
        },
    )
    return Response(text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="marketpulse_screener.csv"'})


def _http(exc: RepoError) -> HTTPException:
    code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/screener/saved")
def list_saved(owner: str = Depends(current_owner)):
    return {"items": [s.to_dict() for s in container.get_repo().list_screens(owner)]}


@router.post("/screener/saved", status_code=201)
def save(body: SaveBody, owner: str = Depends(current_owner)):
    definition = body.definition.model_dump()
    try:
        definition["filters"] = screener.validate_filters(definition["filters"])  # never store an invalid screen
        sc = container.get_repo().create_screen(owner, body.name, definition)
    except screener.ScreenError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except (ConflictError, LimitError, NotFoundError) as e:
        raise _http(e) from None
    return sc.to_dict()


@router.delete("/screener/saved/{screen_id}", status_code=204)
def delete_saved(screen_id: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_screen(owner, screen_id)
    except RepoError as e:
        raise _http(e) from None
    return Response(status_code=204)
