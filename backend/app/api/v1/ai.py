from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import current_owner
from app.core.config import get_settings
from app.services import container, research
from app.services.llm import AnthropicClient

router = APIRouter(tags=["ai"])


class ChatBody(BaseModel):
    question: str = Field(min_length=1, max_length=research.MAX_QUESTION)


def _llm():
    s = get_settings()
    return AnthropicClient(s.llm_api_key, s.llm_model) if s.llm_api_key else None


def _answer(question: str, owner: str) -> dict:
    try:
        return research.answer(container.get_repo(), owner, question, container.get_provider().reference_day(), _llm())
    except research.ToolError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/ai/status")
def status():
    on = bool(get_settings().llm_api_key)
    return {"mode": "llm-assisted explanations" if on else "deterministic", "llm_enabled": on, "suggested": research.SUGGESTED,
            "notice": "Facts always come from stored data via validated tools. A language model, when configured, only phrases the explanation.",
            "tools": ["price_summary", "indicators", "compare", "volatility_ranking", "news", "pipeline_status", "watchlists", "saved_screens"]}


@router.post("/ai/chat")
def chat(body: ChatBody, owner: str = Depends(current_owner)):
    return _answer(body.question, owner)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


@router.post("/ai/chat/stream")
def chat_stream(body: ChatBody, owner: str = Depends(current_owner)):
    """Same answer as /ai/chat, delivered as SSE events (meta, fact*, explanation, sources, done) so the UI can render progressively.
    Errors in planning are returned as an `error` event; validation errors still use a normal 4xx."""
    a = _answer(body.question, owner)

    def gen() -> Iterator[str]:
        yield _sse("meta", {"intent": a["intent"], "symbols": a["symbols"], "range": a["range"], "tools": a["tools"], "refused": a["refused"]})
        for f in a["facts"]:
            yield _sse("fact", f)
        if a["explanation"]:
            yield _sse("explanation", {"text": a["explanation"], "mode": a["explanation_mode"], "llm_error": a["llm_error"]})
        yield _sse("sources", {"sources": a["sources"], "caveats": a["caveats"]})
        yield _sse("done", {"generated_at": a["generated_at"]})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
