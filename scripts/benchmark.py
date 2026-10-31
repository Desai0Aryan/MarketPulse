"""Deterministic micro-benchmarks. Prints measured numbers for THIS machine only; nothing is hard-coded.

    python scripts/benchmark.py            # from the backend/ directory
"""
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.analytics.pipeline import compute_indicator_rows  # noqa: E402
from app.ingestion.providers.mock import MockProvider  # noqa: E402
from app.ingestion.service import IngestionService  # noqa: E402
from app.storage.memory import MemoryRepository  # noqa: E402


def timed(fn, repeat=5):
    xs = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    return statistics.median(xs), min(xs), max(xs)


def main() -> None:
    p = MockProvider(date(2026, 10, 23), 1300)
    bars = p.history("NVDA")
    med, lo, hi = timed(lambda: compute_indicator_rows(bars))
    print(f"indicators: 1300 bars x 15 columns   median {med:.1f} ms (min {lo:.1f}, max {hi:.1f}, n=5)")

    def ingest():
        svc = IngestionService(p, MemoryRepository())
        run = svc.run("backfill")
        return run.stats["inserted"]

    t = time.perf_counter()
    n = ingest()
    dt = time.perf_counter() - t
    print(f"ingestion (memory repo): {n} bars in {dt * 1000:.0f} ms = {n / dt:,.0f} bars/s (includes validation + indicators)")

    repo = MemoryRepository()
    IngestionService(p, repo).run("backfill")
    repo2 = MemoryRepository()
    svc = IngestionService(p, repo2)
    svc.run("backfill")
    med, lo, hi = timed(lambda: repo2.get_bars("AAPL", date(2026, 1, 1), date(2026, 10, 23)))
    print(f"query get_bars (memory, ~210 rows)   median {med:.2f} ms (min {lo:.2f}, max {hi:.2f}, n=5)")
    print("PostgreSQL query latency: run EXPLAIN ANALYZE per docs/database.md against a live database.")


if __name__ == "__main__":
    main()
