"""Plain domain objects shared by ingestion, storage and the API (no framework imports)."""

from __future__ import annotations

from decimal import Decimal
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


@dataclass
class SavedScreen:
    id: int
    owner: str
    name: str
    definition: dict  # validated screener filters + sort + kind

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "definition": self.definition}


@dataclass
class Portfolio:
    id: int
    owner: str
    name: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


@dataclass
class Txn:
    """One paper-portfolio ledger entry. `id == 0` means "not yet stored".

    kind: deposit | withdraw (use `amount`) or buy | sell (use `symbol`, `quantity`, `price`, `fee`).
    """

    id: int
    portfolio_id: int
    day: date
    kind: str
    symbol: str | None = None
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    amount: Decimal = Decimal(0)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "day": self.day.isoformat(), "kind": self.kind, "symbol": self.symbol,
            "quantity": float(self.quantity), "price": float(self.price), "fee": float(self.fee),
            "amount": float(self.amount), "note": self.note,
        }


@dataclass
class Alert:
    id: int
    owner: str
    symbol: str
    kind: str  # see app.services.alerts.KINDS
    threshold: float
    window: int | None = None  # SMA window for cross_* kinds
    cooldown_days: int = 1
    enabled: bool = True
    note: str = ""
    # engine state ------------------------------------------------------
    last_observed_day: date | None = None  # newest session already evaluated (never evaluated twice)
    last_condition: bool | None = None  # condition value at that session; None = never baselined
    fired_in_episode: bool = False  # fired since the condition last became false
    last_fired_day: date | None = None
    created_day: date | None = None

    @property
    def status(self) -> str:
        if not self.enabled:
            return "paused"
        return "triggered" if self.fired_in_episode else "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "symbol": self.symbol, "kind": self.kind, "threshold": self.threshold, "window": self.window,
            "cooldown_days": self.cooldown_days, "enabled": self.enabled, "note": self.note, "status": self.status,
            "waiting_for_reset": bool(self.enabled and self.last_condition and not self.fired_in_episode),
            "last_observed_day": self.last_observed_day.isoformat() if self.last_observed_day else None,
            "last_fired_day": self.last_fired_day.isoformat() if self.last_fired_day else None,
            "created_day": self.created_day.isoformat() if self.created_day else None,
        }


@dataclass
class AlertEvent:
    id: int
    alert_id: int
    owner: str
    symbol: str
    kind: str
    observed_day: date  # the stored session whose data satisfied the condition
    observed_value: float
    threshold: float
    message: str
    evaluated_at: datetime
    read: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "alert_id": self.alert_id, "symbol": self.symbol, "kind": self.kind,
            "observed_day": self.observed_day.isoformat(), "observed_value": self.observed_value,
            "threshold": self.threshold, "message": self.message, "evaluated_at": self.evaluated_at.isoformat(), "read": self.read,
        }


@dataclass
class Article:
    """A news article. `symbols` holds [{"symbol", "relevance"}]; sentiment fields are filled by the scoring step."""

    id: int
    dedup_key: str
    provider: str
    headline: str
    source: str
    published_at: datetime
    url: str | None = None
    summary: str = ""
    symbols: list[dict] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_category: str | None = None
    sentiment_method: str | None = None
    sentiment_version: str | None = None
    sentiment_at: datetime | None = None
    simulated: bool = False  # True when the article text was generated by the demo feed, not published by a news source

    def relevance(self, symbol: str) -> float | None:
        return next((x["relevance"] for x in self.symbols if x["symbol"] == symbol), None)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "headline": self.headline, "source": self.source, "provider": self.provider,
            "published_at": self.published_at.isoformat(), "url": self.url, "summary": self.summary, "symbols": self.symbols,
            "simulated": self.simulated,
            "sentiment": None if self.sentiment_score is None else {
                "score": self.sentiment_score, "category": self.sentiment_category, "method": self.sentiment_method,
                "version": self.sentiment_version, "analysed_at": self.sentiment_at.isoformat() if self.sentiment_at else None,
            },
        }


@dataclass
class BacktestRecord:
    id: int
    owner: str
    symbol: str
    strategy: str
    config: dict
    result: dict
    created_at: datetime

    def summary(self) -> dict:
        m = self.result.get("metrics", {})
        return {"id": self.id, "symbol": self.symbol, "strategy": self.strategy, "created_at": self.created_at.isoformat(),
                "config": self.config, "total_return": m.get("total_return"), "max_drawdown": m.get("max_drawdown"),
                "completed_trades": m.get("completed_trades"), "buy_hold_return": self.result.get("buy_hold_metrics", {}).get("total_return")}
