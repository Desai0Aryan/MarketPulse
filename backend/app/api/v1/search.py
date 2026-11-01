from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import container
from app.services.search import search_instruments

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=40), limit: int = Query(10, ge=1, le=25)):
    items = search_instruments(container.get_repo().get_instruments(), q, limit)
    return {"query": q, "count": len(items), "items": items}
