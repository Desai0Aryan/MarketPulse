"""Plain domain objects shared by ingestion, storage and the API (no framework imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Rejection:
    """A record that failed validation (severity="error", not stored as a price)
    or looked suspicious but was kept (severity="warning")."""

    symbol: str
    day: date | None
    code: str
    severity: str  # "error" | "warning"
    detail: str
    raw: dict | None = None


@dataclass
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0  # duplicate attempts: identical to what is already stored
    earliest_changed: date | None = None  # earliest day that was inserted or corrected


@dataclass(frozen=True)
class Checkpoint:
    symbol: str
    last_day: date
    updated_at: datetime
    run_id: int | None


@dataclass
class RunRecord:
    id: int
    mode: str  # "incremental" | "backfill" | "reindex"
    trigger: str  # "manual" | "scheduler" | "cli"
    provider: str
    status: str  # "running" | "success" | "partial" | "failed"
    symbols: list[str]
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    error: str | None = None
    params: dict = field(default_factory=dict)

    def to_dict(self, include_events: bool = False) -> dict:
        d = {
            "id": self.id,
            "mode": self.mode,
            "trigger": self.trigger,
            "provider": self.provider,
            "status": self.status,
            "symbols": self.symbols,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.stats.get("duration_ms"),
            "stats": self.stats,
            "params": self.params,
            "error": self.error,
        }
        if include_events:
            d["events"] = self.events
        return d


class RepoError(Exception):
    """Base class for expected persistence errors (mapped to HTTP status codes by the API)."""


class NotFoundError(RepoError):
    pass


class ConflictError(RepoError):
    pass


class LimitError(RepoError):
    pass


@dataclass
class Watchlist:
    id: int
    owner: str
    name: str
    is_default: bool
    symbols: list[str]  # ordered

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "is_default": self.is_default, "symbols": list(self.symbols)}
