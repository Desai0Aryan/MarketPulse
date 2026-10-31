"""Ingestion orchestration: fetch -> normalise/validate -> idempotent upsert -> indicators -> checkpoint."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, timedelta

from app.analytics.pipeline import compute_indicator_rows
from app.domain import RunRecord, utcnow
from app.ingestion.providers.base import MarketDataProvider
from app.ingestion.retry import RateLimiter, RetryPolicy, call_with_retry
from app.processing.validation import normalize_symbol, validate_bars
from app.storage.base import Repository

log = logging.getLogger("marketpulse.ingestion")

# Incremental runs re-fetch a few sessions before the checkpoint so late provider corrections are caught.
LOOKBACK_DAYS = 7
MAX_BACKFILL_DAYS = 366 * 6


class JobBusyError(RuntimeError):
    """Another ingestion job is already running."""


class IngestionService:
    def __init__(
        self,
        provider: MarketDataProvider,
        repo: Repository,
        *,
        policy: RetryPolicy | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.repo = repo
        self.policy = policy or RetryPolicy()
        self.limiter = limiter or RateLimiter(per_second=0)
        self._sleep = sleep
        self._lock = threading.Lock()  # one job at a time per process (duplicate-job protection)
        self.current_run_id: int | None = None

    # ------------------------------------------------------------------ public
    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def known_symbols(self) -> list[str]:
        return [i.symbol for i in self.provider.instruments()]

    def run(
        self,
        mode: str = "incremental",
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        trigger: str = "manual",
    ) -> RunRecord:
        """Synchronous run. Raises JobBusyError if another job holds the lock."""
        run = self.begin(mode, symbols, start, end, trigger)
        return self.execute(run, start, end)

    def begin(
        self,
        mode: str,
        symbols: list[str] | None,
        start: date | None,
        end: date | None,
        trigger: str,
    ) -> RunRecord:
        """Validate parameters, take the job lock and create the run record (so callers can return its id)."""
        if mode not in ("incremental", "backfill", "reindex"):
            raise ValueError(f"unknown mode {mode!r}")
        universe = self.known_symbols()
        syms = [normalize_symbol(s) for s in (symbols or universe)]
        unknown = [s for s in syms if s not in universe]
        if unknown:
            raise ValueError(f"unknown symbols: {', '.join(unknown)}")
        if start and end and start > end:
            raise ValueError("start must be on or before end")
        if mode == "backfill" and start and (end or self.provider.reference_day()) - start > timedelta(days=MAX_BACKFILL_DAYS):
            raise ValueError("backfill range is limited to 6 years")
        if not self._lock.acquire(blocking=False):
            raise JobBusyError("an ingestion job is already running")
        try:
            self.repo.upsert_instruments(self.provider.instruments())
            params = {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None}
            run = self.repo.create_run(mode, trigger, self.provider.name, syms, params)
            self.current_run_id = run.id
            return run
        except Exception:
            self._lock.release()
            raise

    def execute(self, run: RunRecord, start: date | None = None, end: date | None = None) -> RunRecord:
        """Run a job created by `begin`. Always releases the lock."""
        t0 = time.perf_counter()
        totals = dict(inserted=0, updated=0, unchanged=0, rejected=0, warnings=0, retries=0, symbols_ok=0, symbols_failed=0)
        per_symbol: dict[str, dict] = {}
        try:
            self.repo.append_event(run, "info", f"{run.mode} run started for {len(run.symbols)} symbols")
            for sym in run.symbols:
                info = self._process_symbol(run, sym, start, end)
                per_symbol[sym] = info
                if info.get("error"):
                    totals["symbols_failed"] += 1
                else:
                    totals["symbols_ok"] += 1
                for k in ("inserted", "updated", "unchanged", "rejected", "warnings", "retries"):
                    totals[k] += info.get(k, 0)
            run.status = (
                "success" if totals["symbols_failed"] == 0 else "failed" if totals["symbols_ok"] == 0 else "partial"
            )
        except Exception as exc:  # unexpected: never leave a run stuck in "running"
            log.exception("ingestion run crashed")
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            run.stats = {**totals, "duration_ms": round((time.perf_counter() - t0) * 1000, 1), "per_symbol": per_symbol}
            self.repo.append_event(run, "info" if run.status == "success" else "warn", f"run finished: {run.status}")
            self.repo.finish_run(run)
            self.current_run_id = None
            self._lock.release()
        log.info("ingestion finished", extra={"path": f"run={run.id} status={run.status}"})
        return run

    # ----------------------------------------------------------------- internals
    def _fetch_start(self, run: RunRecord, sym: str, start: date | None) -> date | None:
        if run.mode == "backfill":
            return start
        cp = self.repo.get_checkpoint(sym)
        return cp.last_day - timedelta(days=LOOKBACK_DAYS) if cp else start

    def _process_symbol(self, run: RunRecord, sym: str, start: date | None, end: date | None) -> dict:
        t0 = time.perf_counter()
        info: dict = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0, "warnings": 0, "retries": 0}
        try:
            if run.mode == "reindex":
                bars = self.repo.get_bars(sym)
                n = self.repo.replace_indicators(sym, date.min, compute_indicator_rows(bars))
                info["indicator_rows"] = n
                self.repo.append_event(run, "info", f"reindexed {n} indicator rows", sym)
            else:
                self.limiter.acquire()
                fetch_start = self._fetch_start(run, sym, start)
                raw, retries = call_with_retry(
                    lambda: self.provider.history(sym, fetch_start, end), self.policy, sleep=self._sleep
                )
                info["retries"] = retries
                info["fetched"] = len(raw)
                prev = self.repo.last_bar_before(sym, raw[0].day) if raw else None
                result = validate_bars(sym, raw, prev_close=prev.close if prev else None)
                info["rejected"] = len(result.rejected)
                info["warnings"] = len(result.warnings)
                if result.all_flags:
                    self.repo.add_rejections(run.id, result.all_flags)
                    for r in result.rejected[:3]:
                        self.repo.append_event(run, "warn", f"rejected {r.day}: {r.code}", sym)
                up = self.repo.upsert_bars(sym, result.accepted, run.id)
                info.update(inserted=up.inserted, updated=up.updated, unchanged=up.unchanged)
                if up.updated:
                    self.repo.append_event(run, "warn", f"{up.updated} historical bars corrected; recomputing indicators", sym)
                if up.earliest_changed:
                    # Indicators from the earliest changed bar onward can differ; earlier ones cannot.
                    rows = compute_indicator_rows(self.repo.get_bars(sym))
                    self.repo.replace_indicators(sym, up.earliest_changed, rows)
                if result.accepted:
                    self.repo.set_checkpoint(sym, max(b.day for b in result.accepted), run.id)
                self.repo.append_event(
                    run, "info", f"fetched {len(raw)}, +{up.inserted} new, ~{up.updated} corrected, ={up.unchanged} unchanged", sym
                )
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"[:200]
            info["error"] = msg
            info["retries"] = getattr(exc, "retries_used", info["retries"])
            self.repo.append_event(run, "error", f"failed: {msg}", sym)
            log.warning("symbol failed", extra={"path": f"{sym} {msg}"})
        info["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        info["finished_at"] = utcnow().isoformat()
        return info
