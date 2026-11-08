from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import current_owner
from app.api.v1.pipeline import require_ops
from app.domain import ConflictError, NotFoundError, RepoError, utcnow
from app.processing.validation import normalize_symbol
from app.services import alerts as al
from app.services import container

router = APIRouter(tags=["alerts"])


def _http(exc: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422, str(exc))


class AlertBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    kind: str
    threshold: float = 0
    window: int | None = None
    cooldown_days: int = Field(1, ge=0, le=30)
    note: str = Field("", max_length=200)


class AlertPatch(BaseModel):
    kind: str | None = None
    threshold: float | None = None
    window: int | None = None
    cooldown_days: int | None = Field(None, ge=0, le=30)
    enabled: bool | None = None
    note: str | None = Field(None, max_length=200)


class ReadBody(BaseModel):
    ids: list[int] | None = Field(None, max_length=500)  # null = all


@router.get("/alerts/kinds")
def kinds():
    return {"items": [{"kind": k, "label": al.LABELS[k], "crossing": k in al.CROSS} for k in al.KINDS], "max_alerts": al.MAX_ALERTS}


@router.get("/alerts")
def list_alerts(owner: str = Depends(current_owner)):
    return {"items": [a.to_dict() for a in container.get_repo().list_alerts(owner)]}


@router.post("/alerts", status_code=201)
def create(body: AlertBody, owner: str = Depends(current_owner)):
    repo = container.get_repo()
    sym = normalize_symbol(body.symbol)
    if sym not in {i.symbol for i in repo.get_instruments()}:
        raise HTTPException(404, f"Unknown symbol '{body.symbol}'")
    try:
        a = al.new_alert(owner, sym, body.kind, body.threshold, body.window, body.cooldown_days, body.note, repo.get_bars(sym))
        return repo.create_alert(owner, a).to_dict()
    except (al.AlertError, RepoError) as e:
        raise _http(e) from None


@router.patch("/alerts/{alert_id}")
def update(alert_id: int, body: AlertPatch, owner: str = Depends(current_owner)):
    repo = container.get_repo()
    try:
        cur = repo.get_alert(owner, alert_id)
        kind = body.kind or cur.kind
        thr = cur.threshold if body.threshold is None else body.threshold
        win = cur.window if body.window is None else body.window
        cd = cur.cooldown_days if body.cooldown_days is None else body.cooldown_days
        thr, win = al.validate_definition(kind, thr, win, cd)
        enabled = cur.enabled if body.enabled is None else body.enabled
        fields: dict = {"kind": kind, "threshold": thr, "window": win, "cooldown_days": cd, "enabled": enabled}
        if body.note is not None:
            fields["note"] = body.note.strip()
        redefined = (kind, thr, win) != (cur.kind, cur.threshold, cur.window)
        resumed = enabled and not cur.enabled
        if redefined or resumed:
            # Re-baseline: the new/resumed alert must not fire for state that already existed or sessions it was off for.
            tmp = cur.__class__(**{**cur.__dict__, **fields})
            b = al.baseline(tmp, repo.get_bars(cur.symbol))
            fields.update(last_observed_day=b.last_observed_day, last_condition=b.last_condition, fired_in_episode=False)
        return repo.update_alert(owner, alert_id, fields).to_dict()
    except (al.AlertError, RepoError) as e:
        raise _http(e) from None


@router.delete("/alerts/{alert_id}", status_code=204)
def delete(alert_id: int, owner: str = Depends(current_owner)):
    try:
        container.get_repo().delete_alert(owner, alert_id)
    except RepoError as e:
        raise _http(e) from None
    return Response(status_code=204)


@router.get("/alerts/events")
def events(alert_id: int | None = None, limit: int = Query(50, ge=1, le=200), owner: str = Depends(current_owner)):
    return {"items": [e.to_dict() for e in container.get_repo().list_events(owner, alert_id, limit)]}


@router.post("/alerts/evaluate", dependencies=[Depends(require_ops)])
def evaluate_now():
    """Evaluate all enabled alerts against stored data now (also runs after every successful ingestion)."""
    return {"evaluated_at": utcnow().isoformat(), **al.evaluate_all(container.get_repo())}


@router.get("/notifications")
def notifications(limit: int = Query(20, ge=1, le=100), owner: str = Depends(current_owner)):
    repo = container.get_repo()
    return {"unread": repo.unread_count(owner), "items": [e.to_dict() for e in repo.list_events(owner, None, limit)]}


@router.post("/notifications/read")
def mark_read(body: ReadBody, owner: str = Depends(current_owner)):
    return {"marked": container.get_repo().mark_events_read(owner, body.ids)}
