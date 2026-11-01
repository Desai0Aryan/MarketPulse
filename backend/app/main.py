from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import market, pipeline, search, stocks, watchlists
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import container
from app.services.watchlists import ensure_default

log = logging.getLogger("marketpulse")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    log.info("starting", extra={"path": f"provider={s.data_provider} storage={s.storage}"})
    if s.auto_seed and s.is_demo:
        repo = container.get_repo()
        if not repo.bar_counts() or all(n == 0 for n, _, _ in repo.bar_counts().values()):
            run = container.get_ingestion().run("backfill", trigger="startup")
            log.info("demo seed finished", extra={"path": f"run={run.id} status={run.status}"})
    ensure_default(container.get_repo())
    yield
    log.info("shutdown complete")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=f"{s.app_name} API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["x-request-id"] = rid
        log.info("request", extra={"request_id": rid, "path": request.url.path, "status": response.status_code, "duration_ms": ms})
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "service": s.app_name, "provider": s.data_provider, "demo": s.is_demo}

    @app.get("/ready", tags=["ops"])
    def ready():
        repo = container.get_repo()
        checks = {"database": "ok" if repo.ping() else "down", "provider": "ok" if container.get_provider().ping() else "down"}
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", "checks": checks})

    app.include_router(stocks.router, prefix="/api/v1")
    app.include_router(market.router, prefix="/api/v1")
    app.include_router(pipeline.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(watchlists.router, prefix="/api/v1")
    return app


app = create_app()
