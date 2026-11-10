from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services import events

router = APIRouter(tags=["live"])


@router.get("/events")
def live_events():
    """Server-sent events: `hello`, `ingestion` (run finished), `alert` (new alert events), `news`; `: heartbeat` comments every 15 s.
    The browser's EventSource reconnects automatically; the UI also polls as a fallback."""
    return StreamingResponse(events.stream(events.get_bus()), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
