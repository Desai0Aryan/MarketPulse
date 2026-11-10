from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.pipeline import require_ops
from app.core.config import get_settings
from app.processing.validation import normalize_symbol
from app.services import container
from app.services import news as nw

router = APIRouter(tags=["news"])


def make_provider():
    s = get_settings()
    if s.news_provider == "sample":
        return nw.SampleNewsProvider(container.get_repo())
    if s.news_provider == "file":
        if not s.news_file:
            raise HTTPException(409, "MP_NEWS_FILE is not set")
        return nw.FileNewsProvider(s.news_file)
    return None


def _day(d: date | None, end: bool) -> datetime | None:
    return None if d is None else datetime.combine(d, time.max if end else time.min, tzinfo=UTC)


@router.get("/news")
def list_news(
    symbol: str | None = Query(None, max_length=16),
    source: str | None = Query(None, max_length=80),
    start: date | None = None,
    end: date | None = None,
    min_relevance: float = Query(0.0, ge=0, le=1),
    sentiment: Literal["positive", "neutral", "negative"] | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=5000),
):
    if start and end and start > end:
        raise HTTPException(422, "start must not be after end")
    repo = container.get_repo()
    sym = normalize_symbol(symbol) if symbol else None
    items, total = repo.list_articles(sym, source, _day(start, False), _day(end, True), min_relevance, sentiment, limit, offset)
    s = get_settings()
    return {
        "provider": s.news_provider, "simulated": s.news_provider == "sample", "total": total, "items": [a.to_dict() for a in items],
        "sentiment_notice": nw.SENTIMENT_NOTICE, "sentiment_method": f"{nw.SENTIMENT_METHOD} v{nw.SENTIMENT_VERSION}",
        "attribution": "Articles belong to their publishers. Only headline, source, time and link are shown.",
        "notice": "Demo feed: headlines are generated from simulated price moves, not real news." if s.news_provider == "sample" else None,
    }


@router.get("/news/sources")
def sources():
    return {"items": [{"source": s, "count": n} for s, n in container.get_repo().list_sources()]}


@router.get("/news/summary")
def summary(symbol: str = Query(max_length=16)):
    sym = normalize_symbol(symbol)
    items, total = container.get_repo().list_articles(sym, None, None, None, 0.4, None, 200, 0)
    return {"symbol": sym, "total": total, **nw.sentiment_summary(items)}


@router.post("/news/refresh", dependencies=[Depends(require_ops)])
def refresh():
    p = make_provider()
    if p is None:
        raise HTTPException(409, "News ingestion is disabled (MP_NEWS_PROVIDER=off)")
    try:
        return nw.refresh(container.get_repo(), p)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e)) from None
