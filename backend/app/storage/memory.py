from __future__ import annotations

import threading
from bisect import bisect_left
from collections import defaultdict
from datetime import date

from app.domain import (
    Checkpoint, ConflictError, LimitError, NotFoundError, Rejection, RunRecord, UpsertResult, Watchlist, utcnow,
)
from app.ingestion.providers.base import Bar, Instrument


class MemoryRepository:
    """In-process repository with the same semantics as the SQL one. Data is lost on restart."""

    kind = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instruments: dict[str, Instrument] = {}
        self._bars: dict[str, dict[date, Bar]] = defaultdict(dict)
        self._ind: dict[str, dict[date, dict]] = defaultdict(dict)
        self._cp: dict[str, Checkpoint] = {}
        self._runs: dict[int, RunRecord] = {}
        self._rej: list[tuple[int, Rejection]] = []
        self._next_run = 1
        self._wl: dict[int, Watchlist] = {}
        self._next_wl = 1

    def ping(self) -> bool:
        return True

    # instruments ------------------------------------------------------
    def upsert_instruments(self, items: list[Instrument]) -> None:
        with self._lock:
            for i in items:
                self._instruments[i.symbol] = i

    def get_instruments(self) -> list[Instrument]:
        with self._lock:
            return sorted(self._instruments.values(), key=lambda i: i.symbol)

    # prices -----------------------------------------------------------
    def upsert_bars(self, symbol: str, bars: list[Bar], run_id: int | None) -> UpsertResult:
        res = UpsertResult()
        with self._lock:
            store = self._bars[symbol]
            for b in bars:
                old = store.get(b.day)
                if old is None:
                    res.inserted += 1
                elif old == b:
                    res.unchanged += 1
                    continue
                else:
                    res.updated += 1
                store[b.day] = b
                if res.earliest_changed is None or b.day < res.earliest_changed:
                    res.earliest_changed = b.day
        return res

    def get_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        with self._lock:
            rows = sorted(self._bars.get(symbol, {}).values(), key=lambda b: b.day)
        return [b for b in rows if (start is None or b.day >= start) and (end is None or b.day <= end)]

    def last_bar_before(self, symbol: str, day: date) -> Bar | None:
        rows = self.get_bars(symbol, end=None)
        days = [b.day for b in rows]
        i = bisect_left(days, day)
        return rows[i - 1] if i > 0 else None

    # checkpoints ------------------------------------------------------
    def get_checkpoint(self, symbol: str) -> Checkpoint | None:
        return self._cp.get(symbol)

    def set_checkpoint(self, symbol: str, last_day: date, run_id: int | None) -> None:
        with self._lock:
            cur = self._cp.get(symbol)
            # Checkpoints only move forward; a backfill of old data must not rewind them.
            if cur is None or last_day >= cur.last_day:
                self._cp[symbol] = Checkpoint(symbol, last_day, utcnow(), run_id)

    def list_checkpoints(self) -> list[Checkpoint]:
        return sorted(self._cp.values(), key=lambda c: c.symbol)

    # indicators -------------------------------------------------------
    def replace_indicators(self, symbol: str, from_day: date, rows: list[dict]) -> int:
        with self._lock:
            store = self._ind[symbol]
            for d in [d for d in store if d >= from_day]:
                del store[d]
            for r in rows:
                if r["day"] >= from_day:
                    store[r["day"]] = r
            return sum(1 for r in rows if r["day"] >= from_day)

    def get_indicators(self, symbol: str, start: date | None = None, end: date | None = None) -> list[dict]:
        with self._lock:
            rows = sorted(self._ind.get(symbol, {}).values(), key=lambda r: r["day"])
        return [r for r in rows if (start is None or r["day"] >= start) and (end is None or r["day"] <= end)]

    # runs -------------------------------------------------------------
    def create_run(self, mode: str, trigger: str, provider: str, symbols: list[str], params: dict) -> RunRecord:
        with self._lock:
            run = RunRecord(self._next_run, mode, trigger, provider, "running", list(symbols), utcnow(), params=dict(params))
            self._runs[run.id] = run
            self._next_run += 1
            return run

    def finish_run(self, run: RunRecord) -> None:
        with self._lock:
            run.finished_at = utcnow()
            self._runs[run.id] = run

    def append_event(self, run: RunRecord, level: str, msg: str, symbol: str | None = None) -> None:
        with self._lock:
            run.events.append({"ts": utcnow().isoformat(), "level": level, "msg": msg, "symbol": symbol})

    def get_run(self, run_id: int) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_runs(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[RunRecord], int]:
        with self._lock:
            runs = sorted(self._runs.values(), key=lambda r: r.id, reverse=True)
        if status:
            runs = [r for r in runs if r.status == status]
        return runs[offset : offset + limit], len(runs)

    # rejections -------------------------------------------------------
    def add_rejections(self, run_id: int, items: list[Rejection]) -> None:
        with self._lock:
            self._rej.extend((run_id, i) for i in items)

    def list_rejections(self, run_id: int | None = None, limit: int = 100) -> list[Rejection]:
        with self._lock:
            rows = [r for rid, r in self._rej if run_id is None or rid == run_id]
        return rows[-limit:][::-1]

    def rejection_counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        with self._lock:
            for _, r in self._rej:
                out[f"{r.severity}:{r.code}"] += 1
        return dict(out)

    def bar_counts(self) -> dict[str, tuple[int, date | None, date | None]]:
        with self._lock:
            return {s: (len(b), min(b) if b else None, max(b) if b else None) for s, b in self._bars.items()}

    # watchlists -------------------------------------------------------
    MAX_LISTS = 20
    MAX_ITEMS = 100

    def _get_wl(self, owner: str, wl_id: int) -> Watchlist:
        wl = self._wl.get(wl_id)
        if wl is None or wl.owner != owner:  # same error for "missing" and "someone else's": no existence leak
            raise NotFoundError("Watchlist not found")
        return wl

    @staticmethod
    def _copy(wl: Watchlist) -> Watchlist:
        return Watchlist(wl.id, wl.owner, wl.name, wl.is_default, list(wl.symbols))

    def list_watchlists(self, owner: str) -> list[Watchlist]:
        with self._lock:
            return [self._copy(w) for w in sorted(self._wl.values(), key=lambda w: w.id) if w.owner == owner]

    def create_watchlist(self, owner: str, name: str) -> Watchlist:
        with self._lock:
            mine = [w for w in self._wl.values() if w.owner == owner]
            if len(mine) >= self.MAX_LISTS:
                raise LimitError(f"At most {self.MAX_LISTS} watchlists")
            if any(w.name.lower() == name.lower() for w in mine):
                raise ConflictError(f"A watchlist named '{name}' already exists")
            wl = Watchlist(self._next_wl, owner, name, is_default=not mine, symbols=[])
            self._wl[wl.id] = wl
            self._next_wl += 1
            return self._copy(wl)

    def update_watchlist(self, owner: str, wl_id: int, name: str | None = None, make_default: bool = False) -> Watchlist:
        with self._lock:
            wl = self._get_wl(owner, wl_id)
            if name is not None and name.lower() != wl.name.lower():
                if any(w.name.lower() == name.lower() for w in self._wl.values() if w.owner == owner):
                    raise ConflictError(f"A watchlist named '{name}' already exists")
            if name is not None:
                wl.name = name
            if make_default:
                for w in self._wl.values():
                    if w.owner == owner:
                        w.is_default = w.id == wl_id
            return self._copy(wl)

    def delete_watchlist(self, owner: str, wl_id: int) -> None:
        with self._lock:
            wl = self._get_wl(owner, wl_id)
            del self._wl[wl_id]
            rest = sorted((w for w in self._wl.values() if w.owner == owner), key=lambda w: w.id)
            if wl.is_default and rest:
                rest[0].is_default = True  # always keep exactly one default

    def add_watchlist_item(self, owner: str, wl_id: int, symbol: str) -> Watchlist:
        with self._lock:
            wl = self._get_wl(owner, wl_id)
            if symbol not in self._instruments:
                raise NotFoundError(f"Unknown symbol '{symbol}'")
            if symbol not in wl.symbols:  # idempotent
                if len(wl.symbols) >= self.MAX_ITEMS:
                    raise LimitError(f"At most {self.MAX_ITEMS} symbols per watchlist")
                wl.symbols.append(symbol)
            return self._copy(wl)

    def remove_watchlist_item(self, owner: str, wl_id: int, symbol: str) -> Watchlist:
        with self._lock:
            wl = self._get_wl(owner, wl_id)
            if symbol not in wl.symbols:
                raise NotFoundError(f"{symbol} is not in this watchlist")
            wl.symbols.remove(symbol)
            return self._copy(wl)

    def reorder_watchlist(self, owner: str, wl_id: int, symbols: list[str]) -> Watchlist:
        with self._lock:
            wl = self._get_wl(owner, wl_id)
            if sorted(symbols) != sorted(wl.symbols):
                raise ConflictError("Order must contain exactly the symbols currently in the watchlist")
            wl.symbols = list(symbols)
            return self._copy(wl)
