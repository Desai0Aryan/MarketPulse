from __future__ import annotations

from datetime import date, timedelta

from app.storage.base import Repository


def sessions_between(a: date, b: date) -> int:
    """Number of weekday sessions after `a` up to and including `b` (holidays are not modelled)."""
    if b <= a:
        return 0
    return sum(1 for i in range(1, (b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def freshness(repo: Repository, reference: date, stale_after_sessions: int = 3) -> list[dict]:
    counts = repo.bar_counts()
    out = []
    for inst in repo.get_instruments():
        n, first, last = counts.get(inst.symbol, (0, None, None))
        cp = repo.get_checkpoint(inst.symbol)
        lag = sessions_between(last, reference) if last else None
        out.append(
            {
                "symbol": inst.symbol,
                "bars": n,
                "first_day": first.isoformat() if first else None,
                "latest_day": last.isoformat() if last else None,
                "lag_sessions": lag,
                "stale": lag is None or lag > stale_after_sessions,
                "checkpoint": cp.last_day.isoformat() if cp else None,
                "checkpoint_updated_at": cp.updated_at.isoformat() if cp else None,
                "checkpoint_run_id": cp.run_id if cp else None,
            }
        )
    return out


def quality_report(repo: Repository, reference: date) -> dict:
    fresh = freshness(repo, reference)
    runs, total_runs = repo.list_runs(limit=200)
    dup = sum(r.stats.get("unchanged", 0) for r in runs)
    rej = repo.rejection_counts()
    failures = [r for r in runs if r.status in ("failed", "partial")]
    return {
        "generated_for": reference.isoformat(),
        "record_counts": {f["symbol"]: f["bars"] for f in fresh},
        "total_bars": sum(f["bars"] for f in fresh),
        "duplicate_attempts": dup,
        "rejections_by_reason": rej,
        "rejected_records": sum(v for k, v in rej.items() if k.startswith("error:")),
        "warnings": sum(v for k, v in rej.items() if k.startswith("warning:")),
        "stale_symbols": [f["symbol"] for f in fresh if f["stale"]],
        "latest_timestamp": max((f["latest_day"] for f in fresh if f["latest_day"]), default=None),
        "ingestion_failures": len(failures),
        "runs_considered": min(total_runs, 200),
        "missing_values": "Indicator columns are NULL until enough history exists (e.g. SMA200 needs 200 bars); price fields are required and never null.",
    }
