from __future__ import annotations

import copy
import dataclasses
import threading
from bisect import bisect_left
from collections import defaultdict
from datetime import date

from app.domain import (
    Checkpoint, ConflictError, LimitError, NotFoundError, Rejection, RunRecord, SavedScreen, UpsertResult, Watchlist, utcnow,
    Alert, AlertEvent, Portfolio, Txn,
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
        self._screens: dict[int, SavedScreen] = {}
        self._next_screen = 1
        self._pf: dict[int, Portfolio] = {}
        self._txns: dict[int, list[Txn]] = {}
        self._next_pf = 1
        self._next_txn = 1
        self._alerts: dict[int, Alert] = {}
        self._events: list[AlertEvent] = []
        self._next_alert = 1
        self._next_event = 1

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

    # saved screens ----------------------------------------------------
    MAX_SCREENS = 25

    def list_screens(self, owner: str) -> list[SavedScreen]:
        with self._lock:
            return [SavedScreen(x.id, x.owner, x.name, copy.deepcopy(x.definition))
                    for x in sorted(self._screens.values(), key=lambda x: x.id) if x.owner == owner]

    def create_screen(self, owner: str, name: str, definition: dict) -> SavedScreen:
        with self._lock:
            mine = [x for x in self._screens.values() if x.owner == owner]
            if len(mine) >= self.MAX_SCREENS:
                raise LimitError(f"At most {self.MAX_SCREENS} saved screens")
            if any(x.name.lower() == name.lower() for x in mine):
                raise ConflictError(f"A screen named '{name}' already exists")
            sc = SavedScreen(self._next_screen, owner, name, copy.deepcopy(definition))
            self._next_screen += 1
            self._screens[sc.id] = sc
            return SavedScreen(sc.id, owner, name, copy.deepcopy(definition))

    def delete_screen(self, owner: str, screen_id: int) -> None:
        with self._lock:
            sc = self._screens.get(screen_id)
            if sc is None or sc.owner != owner:
                raise NotFoundError("Saved screen not found")
            del self._screens[screen_id]

    # portfolios -------------------------------------------------------
    MAX_PORTFOLIOS = 10
    MAX_TXNS = 2000

    def _pf_get(self, owner: str, pid: int) -> Portfolio:
        p = self._pf.get(pid)
        if p is None or p.owner != owner:
            raise NotFoundError("Portfolio not found")
        return p

    def list_portfolios(self, owner: str) -> list[Portfolio]:
        with self._lock:
            return [dataclasses.replace(p) for p in sorted(self._pf.values(), key=lambda p: p.id) if p.owner == owner]

    def create_portfolio(self, owner: str, name: str, initial: Txn | None = None) -> Portfolio:
        with self._lock:
            mine = [p for p in self._pf.values() if p.owner == owner]
            if len(mine) >= self.MAX_PORTFOLIOS:
                raise LimitError(f"At most {self.MAX_PORTFOLIOS} portfolios")
            if any(p.name.lower() == name.lower() for p in mine):
                raise ConflictError(f"A portfolio named '{name}' already exists")
            p = Portfolio(self._next_pf, owner, name)
            self._next_pf += 1
            self._pf[p.id] = p
            self._txns[p.id] = []
            if initial is not None:
                self._append_txn(p.id, initial)
            return dataclasses.replace(p)

    def _append_txn(self, pid: int, txn: Txn) -> Txn:
        t = dataclasses.replace(txn, id=self._next_txn, portfolio_id=pid)
        self._next_txn += 1
        self._txns[pid].append(t)
        return t

    def get_portfolio(self, owner: str, pid: int) -> Portfolio:
        with self._lock:
            return dataclasses.replace(self._pf_get(owner, pid))

    def delete_portfolio(self, owner: str, pid: int) -> None:
        with self._lock:
            self._pf_get(owner, pid)
            del self._pf[pid], self._txns[pid]

    def list_txns(self, owner: str, pid: int) -> list[Txn]:
        with self._lock:
            self._pf_get(owner, pid)
            return [dataclasses.replace(t) for t in self._txns[pid]]

    def add_txn(self, owner: str, pid: int, txn: Txn, validate) -> Txn:
        with self._lock:
            self._pf_get(owner, pid)
            if len(self._txns[pid]) >= self.MAX_TXNS:
                raise LimitError(f"At most {self.MAX_TXNS} transactions per portfolio")
            validate([*self._txns[pid], dataclasses.replace(txn, portfolio_id=pid)])  # raises -> nothing stored
            return dataclasses.replace(self._append_txn(pid, txn))

    def delete_txn(self, owner: str, pid: int, txn_id: int, validate) -> None:
        with self._lock:
            self._pf_get(owner, pid)
            rest = [t for t in self._txns[pid] if t.id != txn_id]
            if len(rest) == len(self._txns[pid]):
                raise NotFoundError("Transaction not found")
            validate(rest)
            self._txns[pid] = rest

    # alerts -----------------------------------------------------------
    MAX_ALERTS = 50
    MAX_EVENTS = 500

    def _alert_get(self, owner: str, alert_id: int) -> Alert:
        a = self._alerts.get(alert_id)
        if a is None or a.owner != owner:
            raise NotFoundError("Alert not found")
        return a

    def list_alerts(self, owner: str) -> list[Alert]:
        with self._lock:
            return [dataclasses.replace(a) for a in sorted(self._alerts.values(), key=lambda a: a.id) if a.owner == owner]

    def create_alert(self, owner: str, alert: Alert) -> Alert:
        with self._lock:
            if sum(1 for a in self._alerts.values() if a.owner == owner) >= self.MAX_ALERTS:
                raise LimitError(f"At most {self.MAX_ALERTS} alerts")
            a = dataclasses.replace(alert, id=self._next_alert, owner=owner)
            self._next_alert += 1
            self._alerts[a.id] = a
            return dataclasses.replace(a)

    def get_alert(self, owner: str, alert_id: int) -> Alert:
        with self._lock:
            return dataclasses.replace(self._alert_get(owner, alert_id))

    def update_alert(self, owner: str, alert_id: int, fields: dict) -> Alert:
        with self._lock:
            a = self._alert_get(owner, alert_id)
            for k, v in fields.items():
                if not hasattr(a, k) or k in ("id", "owner"):
                    raise ValueError(f"cannot update {k}")
                setattr(a, k, v)
            return dataclasses.replace(a)

    def delete_alert(self, owner: str, alert_id: int) -> None:
        with self._lock:
            self._alert_get(owner, alert_id)
            del self._alerts[alert_id]
            self._events = [e for e in self._events if e.alert_id != alert_id]

    def list_enabled_alerts(self) -> list[Alert]:
        with self._lock:
            return [dataclasses.replace(a) for a in sorted(self._alerts.values(), key=lambda a: a.id) if a.enabled]

    def record_evaluation(self, alert_id: int, expected_last_observed_day, ev, now) -> bool:
        """Compare-and-set on last_observed_day: if another evaluation already advanced it, apply nothing."""
        with self._lock:
            a = self._alerts.get(alert_id)
            if a is None or not a.enabled or a.last_observed_day != expected_last_observed_day:
                return False
            a.last_observed_day, a.last_condition = ev.last_observed_day, ev.last_condition
            a.fired_in_episode, a.last_fired_day = ev.fired_in_episode, ev.last_fired_day
            for e in ev.events:
                self._events.append(AlertEvent(self._next_event, a.id, a.owner, a.symbol, a.kind, e["observed_day"],
                                               e["observed_value"], a.threshold, e["message"], now))
                self._next_event += 1
            mine = [e for e in self._events if e.owner == a.owner]
            if len(mine) > self.MAX_EVENTS:
                drop = {e.id for e in mine[: len(mine) - self.MAX_EVENTS]}
                self._events = [e for e in self._events if e.id not in drop]
            return True

    def list_events(self, owner: str, alert_id: int | None = None, limit: int = 50, unread_only: bool = False) -> list[AlertEvent]:
        with self._lock:
            rows = [e for e in self._events if e.owner == owner and (alert_id is None or e.alert_id == alert_id) and (not e.read or not unread_only)]
            return [dataclasses.replace(e) for e in sorted(rows, key=lambda e: e.id, reverse=True)[:limit]]

    def unread_count(self, owner: str) -> int:
        with self._lock:
            return sum(1 for e in self._events if e.owner == owner and not e.read)

    def mark_events_read(self, owner: str, ids: list[int] | None) -> int:
        with self._lock:
            n = 0
            for e in self._events:
                if e.owner == owner and not e.read and (ids is None or e.id in ids):
                    e.read = True
                    n += 1
            return n
