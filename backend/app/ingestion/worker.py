"""Scheduled ingestion worker (separate process from the API).

Uses a plain interval loop with graceful SIGTERM/SIGINT shutdown. A job that is still running when
the next tick arrives is skipped (JobBusyError), so runs never overlap within a process. When the API
and worker are separate processes against PostgreSQL, add a DB advisory lock (noted in docs).
"""

from __future__ import annotations

import logging
import signal
import threading

from app.core.config import get_settings
from app.ingestion.service import JobBusyError
from app.services import container

log = logging.getLogger("marketpulse.worker")


def run_worker() -> None:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    interval = get_settings().ingest_interval_minutes * 60
    svc = container.get_ingestion()
    log.info("worker started", extra={"path": f"every {interval}s"})
    while not stop.is_set():
        try:
            run = svc.run("incremental", trigger="scheduler")
            log.info("scheduled run", extra={"path": f"run={run.id} status={run.status}"})
        except JobBusyError:
            log.info("previous job still running; skipping tick")
        except Exception:  # keep the worker alive
            log.exception("scheduled run failed")
        stop.wait(interval)
    log.info("worker stopped")
