from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import market, stocks
from app.core.config import get_settings
from app.core.logging import configure_logging

log = logging.getLogger("marketpulse")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    log.info("starting", extra={"path": f"provider={s.data_provider}"})
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
        # Part 2 adds a real database check here.
        return {"status": "ready", "checks": {"provider": "ok"}}

    app.include_router(stocks.router, prefix="/api/v1")
    app.include_router(market.router, prefix="/api/v1")
    return app


app = create_app()
