from __future__ import annotations

import hmac
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ingestion.service import JobBusyError
from app.processing.quality import freshness, quality_report
from app.services import container

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def require_ops(x_admin_token: str | None = Header(default=None)) -> None:
    """Guards state-changing operations. With MP_ADMIN_TOKEN set, the header must match.
    Without it, only the development environment may trigger jobs (documented demo profile)."""
    s = get_settings()
    if s.admin_token:
        if not x_admin_token or not hmac.compare_digest(x_admin_token, s.admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token")
    elif s.environment != "development":
        raise HTTPException(status_code=403, detail="Operational actions are disabled: set MP_ADMIN_TOKEN")


class IngestRequest(BaseModel):
    symbols: list[str] | None = Field(default=None, max_length=50)
    mode: Literal["incremental", "reindex"] = "incremental"


class BackfillRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    start: date
    end: date | None = None


def _launch(bg: BackgroundTasks, mode: str, symbols, start, end) -> dict:
    svc = container.get_ingestion()
    try:
        run = svc.begin(mode, symbols, start, end, "manual")
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    bg.add_task(svc.execute, run, start, end)
    return {"run_id": run.id, "status": "running"}


@router.post("/ingest", status_code=202, dependencies=[Depends(require_ops)])
def trigger_ingest(body: IngestRequest, bg: BackgroundTasks):
    return _launch(bg, body.mode, body.symbols, None, None)


@router.post("/backfill", status_code=202, dependencies=[Depends(require_ops)])
def trigger_backfill(body: BackfillRequest, bg: BackgroundTasks):
    return _launch(bg, "backfill", body.symbols, body.start, body.end)


@router.get("/status")
def status():
    svc, repo, provider = container.get_ingestion(), container.get_repo(), container.get_provider()
    runs, total = repo.list_runs(limit=100)
    finished = [r for r in runs if r.status != "running"]
    ok = [r for r in finished if r.status == "success"]
    last_ok = next((r for r in finished if r.status == "success"), None)
    ref = provider.reference_day()
    fresh = freshness(repo, ref)
    durations = [r.stats.get("duration_ms") for r in finished if r.stats.get("duration_ms") is not None]
    return {
        "api": "ok",
        "database": {"kind": repo.kind, "ok": repo.ping()},
        "provider": {"name": provider.name, "data_class": provider.data_class, "ok": provider.ping()},
        "worker": {"busy": svc.busy, "current_run_id": svc.current_run_id, "schedule_minutes": get_settings().ingest_interval_minutes},
        "last_success": last_ok.to_dict() if last_ok else None,
        "totals": {
            "runs": total,
            "success_rate": round(len(ok) / len(finished), 3) if finished else None,
            "inserted": sum(r.stats.get("inserted", 0) for r in finished),
            "updated": sum(r.stats.get("updated", 0) for r in finished),
            "unchanged_duplicates": sum(r.stats.get("unchanged", 0) for r in finished),
            "rejected": sum(r.stats.get("rejected", 0) for r in finished),
            "retries": sum(r.stats.get("retries", 0) for r in finished),
            "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        },
        "freshness": fresh,
        "reference_day": ref.isoformat(),
        "latency_series": [{"run_id": r.id, "duration_ms": r.stats.get("duration_ms"), "status": r.status} for r in reversed(finished[:20])],
        "recent_events": [
            {**e, "run_id": r.id} for r in runs[:5] for e in r.events[-6:]
        ][-20:],
    }


@router.get("/runs")
def list_runs(status: Literal["running", "success", "partial", "failed"] | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    runs, total = container.get_repo().list_runs(status, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "items": [r.to_dict() for r in runs]}


@router.get("/runs/{run_id}")
def run_detail(run_id: int):
    repo = container.get_repo()
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    rej = [{"symbol": r.symbol, "day": r.day.isoformat() if r.day else None, "code": r.code, "severity": r.severity, "detail": r.detail} for r in repo.list_rejections(run_id, 200)]
    return {**run.to_dict(include_events=True), "rejections": rej}


@router.get("/quality")
def quality():
    return quality_report(container.get_repo(), container.get_provider().reference_day())
