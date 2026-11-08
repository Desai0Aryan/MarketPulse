"""PostgreSQL repository (SQLAlchemy 2.0 + psycopg3).

NOTE: written against the documented SQLAlchemy 2.0 API but NOT executed in the Part 2 build
sandbox (no package access). Run the integration tests in tests/test_sql_repo.py against a
real PostgreSQL (`MP_TEST_DATABASE_URL=...`) before relying on it.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    CheckpointRow, IndicatorRow, IngestionRunRow, InstrumentRow, PriceRow, AlertEventRow, AlertRow, PortfolioRow, PortfolioTxnRow, RejectedRecordRow, SavedScreenRow, WatchlistItemRow, WatchlistRow,
)
from app.domain import (
    Checkpoint, ConflictError, LimitError, NotFoundError, Rejection, RunRecord, SavedScreen, UpsertResult, Watchlist, utcnow,
    Alert, AlertEvent, Portfolio, Txn,
)
from app.ingestion.providers.base import Bar, Instrument

_IND_COLS = (
    "sma20", "sma50", "sma200", "ema12", "ema26", "rsi14", "macd", "macd_signal", "macd_hist",
    "bb_lower", "bb_mid", "bb_upper", "atr14", "roc12", "vol20",
)


class SqlRepository:
    kind = "postgres"

    def __init__(self, url: str) -> None:
        # Pooled connections with pre-ping so a restarted database is recovered transparently.
        self.engine = create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True, pool_timeout=10)
        self._Session = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._Session()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # helpers ---------------------------------------------------------
    def _iid(self, s: Session, symbol: str) -> int:
        iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
        if iid is None:
            raise KeyError(f"instrument {symbol} not registered")
        return iid

    # instruments -----------------------------------------------------
    def upsert_instruments(self, items: list[Instrument]) -> None:
        if not items:
            return
        rows = [dict(symbol=i.symbol, name=i.name, exchange=i.exchange, currency=i.currency, kind=i.kind, sector=i.sector) for i in items]
        stmt = pg_insert(InstrumentRow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={c: stmt.excluded[c] for c in ("name", "exchange", "currency", "kind", "sector")},
        )
        with self.session() as s, s.begin():
            s.execute(stmt)

    def get_instruments(self) -> list[Instrument]:
        with self.session() as s:
            rows = s.scalars(select(InstrumentRow).order_by(InstrumentRow.symbol)).all()
            return [Instrument(r.symbol, r.name, r.exchange, r.currency, r.kind, r.sector) for r in rows]

    # prices ----------------------------------------------------------
    @staticmethod
    def _bar(r: PriceRow) -> Bar:
        return Bar(r.day, float(r.open), float(r.high), float(r.low), float(r.close), float(r.adj_close), int(r.volume))

    def upsert_bars(self, symbol: str, bars: list[Bar], run_id: int | None) -> UpsertResult:
        res = UpsertResult()
        if not bars:
            return res
        with self.session() as s, s.begin():  # one transaction: all-or-nothing per symbol
            iid = self._iid(s, symbol)
            lo, hi = min(b.day for b in bars), max(b.day for b in bars)
            existing = {
                r.day: self._bar(r)
                for r in s.scalars(
                    select(PriceRow).where(PriceRow.instrument_id == iid, PriceRow.interval == "1d", PriceRow.day.between(lo, hi))
                )
            }
            changed: list[dict] = []
            for b in bars:
                old = existing.get(b.day)
                if old is None:
                    res.inserted += 1
                elif old == b:
                    res.unchanged += 1
                    continue
                else:
                    res.updated += 1
                if res.earliest_changed is None or b.day < res.earliest_changed:
                    res.earliest_changed = b.day
                changed.append(
                    dict(instrument_id=iid, interval="1d", day=b.day, open=b.open, high=b.high, low=b.low,
                         close=b.close, adj_close=b.adj_close, volume=b.volume, run_id=run_id)
                )
            for i in range(0, len(changed), 2000):  # bulk upsert in chunks
                stmt = pg_insert(PriceRow).values(changed[i : i + 2000])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["instrument_id", "interval", "day"],
                    set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "adj_close", "volume", "run_id")},
                )
                s.execute(stmt)
        return res

    def get_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        with self.session() as s:
            iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
            if iid is None:
                return []
            q = select(PriceRow).where(PriceRow.instrument_id == iid, PriceRow.interval == "1d").order_by(PriceRow.day)
            if start:
                q = q.where(PriceRow.day >= start)
            if end:
                q = q.where(PriceRow.day <= end)
            return [self._bar(r) for r in s.scalars(q)]

    def last_bar_before(self, symbol: str, day: date) -> Bar | None:
        with self.session() as s:
            iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
            if iid is None:
                return None
            r = s.scalar(
                select(PriceRow).where(PriceRow.instrument_id == iid, PriceRow.interval == "1d", PriceRow.day < day)
                .order_by(PriceRow.day.desc()).limit(1)
            )
            return self._bar(r) if r else None

    # checkpoints -----------------------------------------------------
    def get_checkpoint(self, symbol: str) -> Checkpoint | None:
        with self.session() as s:
            row = s.execute(
                select(InstrumentRow.symbol, CheckpointRow)
                .join(CheckpointRow, CheckpointRow.instrument_id == InstrumentRow.id)
                .where(InstrumentRow.symbol == symbol)
            ).first()
            return Checkpoint(row[0], row[1].last_day, row[1].updated_at, row[1].run_id) if row else None

    def set_checkpoint(self, symbol: str, last_day: date, run_id: int | None) -> None:
        with self.session() as s, s.begin():
            iid = self._iid(s, symbol)
            stmt = pg_insert(CheckpointRow).values(instrument_id=iid, last_day=last_day, updated_at=utcnow(), run_id=run_id)
            # Only move forward: a backfill of old data never rewinds the checkpoint.
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id"],
                set_=dict(last_day=stmt.excluded.last_day, updated_at=stmt.excluded.updated_at, run_id=stmt.excluded.run_id),
                where=CheckpointRow.last_day <= stmt.excluded.last_day,
            )
            s.execute(stmt)

    def list_checkpoints(self) -> list[Checkpoint]:
        with self.session() as s:
            rows = s.execute(
                select(InstrumentRow.symbol, CheckpointRow)
                .join(CheckpointRow, CheckpointRow.instrument_id == InstrumentRow.id)
                .order_by(InstrumentRow.symbol)
            ).all()
            return [Checkpoint(sym, cp.last_day, cp.updated_at, cp.run_id) for sym, cp in rows]

    # indicators ------------------------------------------------------
    def replace_indicators(self, symbol: str, from_day: date, rows: list[dict]) -> int:
        keep = [r for r in rows if r["day"] >= from_day]
        with self.session() as s, s.begin():
            iid = self._iid(s, symbol)
            s.execute(delete(IndicatorRow).where(IndicatorRow.instrument_id == iid, IndicatorRow.day >= from_day))
            for i in range(0, len(keep), 2000):
                s.execute(pg_insert(IndicatorRow).values([{**r, "instrument_id": iid} for r in keep[i : i + 2000]]))
        return len(keep)

    def get_indicators(self, symbol: str, start: date | None = None, end: date | None = None) -> list[dict]:
        with self.session() as s:
            iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
            if iid is None:
                return []
            q = select(IndicatorRow).where(IndicatorRow.instrument_id == iid).order_by(IndicatorRow.day)
            if start:
                q = q.where(IndicatorRow.day >= start)
            if end:
                q = q.where(IndicatorRow.day <= end)
            return [{"day": r.day, **{c: getattr(r, c) for c in _IND_COLS}} for r in s.scalars(q)]

    # runs ------------------------------------------------------------
    @staticmethod
    def _run(r: IngestionRunRow) -> RunRecord:
        return RunRecord(r.id, r.mode, r.trigger, r.provider, r.status, list(r.symbols), r.started_at, r.finished_at,
                         dict(r.stats or {}), list(r.events or []), r.error, dict(r.params or {}))

    def create_run(self, mode: str, trigger: str, provider: str, symbols: list[str], params: dict) -> RunRecord:
        with self.session() as s, s.begin():
            row = IngestionRunRow(mode=mode, trigger=trigger, provider=provider, status="running", symbols=symbols,
                                  params=params, stats={}, events=[], started_at=utcnow())
            s.add(row)
            s.flush()
            return self._run(row)

    def finish_run(self, run: RunRecord) -> None:
        with self.session() as s, s.begin():
            row = s.get(IngestionRunRow, run.id)
            run.finished_at = utcnow()
            row.status, row.stats, row.events, row.error, row.finished_at = run.status, run.stats, run.events, run.error, run.finished_at

    def append_event(self, run: RunRecord, level: str, msg: str, symbol: str | None = None) -> None:
        run.events.append({"ts": utcnow().isoformat(), "level": level, "msg": msg, "symbol": symbol})
        with self.session() as s, s.begin():
            row = s.get(IngestionRunRow, run.id)
            row.events = list(run.events)

    def get_run(self, run_id: int) -> RunRecord | None:
        with self.session() as s:
            row = s.get(IngestionRunRow, run_id)
            return self._run(row) if row else None

    def list_runs(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[RunRecord], int]:
        with self.session() as s:
            q = select(IngestionRunRow)
            cq = select(func.count()).select_from(IngestionRunRow)
            if status:
                q, cq = q.where(IngestionRunRow.status == status), cq.where(IngestionRunRow.status == status)
            rows = s.scalars(q.order_by(IngestionRunRow.id.desc()).limit(limit).offset(offset)).all()
            return [self._run(r) for r in rows], s.scalar(cq) or 0

    # rejections ------------------------------------------------------
    def add_rejections(self, run_id: int, items: list[Rejection]) -> None:
        if not items:
            return
        with self.session() as s, s.begin():
            s.add_all(
                RejectedRecordRow(run_id=run_id, symbol=i.symbol, day=i.day, code=i.code, severity=i.severity, detail=i.detail, raw=i.raw)
                for i in items
            )

    def list_rejections(self, run_id: int | None = None, limit: int = 100) -> list[Rejection]:
        with self.session() as s:
            q = select(RejectedRecordRow).order_by(RejectedRecordRow.id.desc()).limit(limit)
            if run_id is not None:
                q = q.where(RejectedRecordRow.run_id == run_id)
            return [Rejection(r.symbol, r.day, r.code, r.severity, r.detail, r.raw) for r in s.scalars(q)]

    def rejection_counts(self) -> dict[str, int]:
        with self.session() as s:
            rows = s.execute(
                select(RejectedRecordRow.severity, RejectedRecordRow.code, func.count()).group_by(RejectedRecordRow.severity, RejectedRecordRow.code)
            ).all()
            return {f"{sev}:{code}": n for sev, code, n in rows}

    def bar_counts(self) -> dict[str, tuple[int, date | None, date | None]]:
        with self.session() as s:
            rows = s.execute(
                select(InstrumentRow.symbol, func.count(PriceRow.day), func.min(PriceRow.day), func.max(PriceRow.day))
                .join(PriceRow, PriceRow.instrument_id == InstrumentRow.id, isouter=True)
                .group_by(InstrumentRow.symbol)
            ).all()
            return {sym: (n, lo, hi) for sym, n, lo, hi in rows}

    # watchlists ------------------------------------------------------
    MAX_LISTS = 20
    MAX_ITEMS = 100

    def _own(self, s: Session, owner: str, wl_id: int) -> WatchlistRow:
        row = s.scalar(select(WatchlistRow).where(WatchlistRow.id == wl_id, WatchlistRow.owner == owner))
        if row is None:  # identical error for missing and foreign lists
            raise NotFoundError("Watchlist not found")
        return row

    def _symbols(self, s: Session, wl_id: int) -> list[str]:
        return list(
            s.scalars(
                select(InstrumentRow.symbol)
                .join(WatchlistItemRow, WatchlistItemRow.instrument_id == InstrumentRow.id)
                .where(WatchlistItemRow.watchlist_id == wl_id)
                .order_by(WatchlistItemRow.position)
            )
        )

    def _wl(self, s: Session, row: WatchlistRow) -> Watchlist:
        return Watchlist(row.id, row.owner, row.name, row.is_default, self._symbols(s, row.id))

    def list_watchlists(self, owner: str) -> list[Watchlist]:
        with self.session() as s:
            rows = s.scalars(select(WatchlistRow).where(WatchlistRow.owner == owner).order_by(WatchlistRow.id)).all()
            return [self._wl(s, r) for r in rows]

    def create_watchlist(self, owner: str, name: str) -> Watchlist:
        try:
            with self.session() as s, s.begin():
                n = s.scalar(select(func.count()).select_from(WatchlistRow).where(WatchlistRow.owner == owner)) or 0
                if n >= self.MAX_LISTS:
                    raise LimitError(f"At most {self.MAX_LISTS} watchlists")
                row = WatchlistRow(owner=owner, name=name, is_default=(n == 0))
                s.add(row)
                s.flush()
                return Watchlist(row.id, owner, name, row.is_default, [])
        except IntegrityError:
            raise ConflictError(f"A watchlist named '{name}' already exists") from None

    def update_watchlist(self, owner: str, wl_id: int, name: str | None = None, make_default: bool = False) -> Watchlist:
        try:
            with self.session() as s, s.begin():
                row = self._own(s, owner, wl_id)
                if name is not None:
                    row.name = name
                if make_default:
                    # clear first so the partial unique index never sees two defaults
                    s.execute(update(WatchlistRow).where(WatchlistRow.owner == owner).values(is_default=False))
                    s.flush()
                    row.is_default = True
                s.flush()
                return self._wl(s, row)
        except IntegrityError:
            raise ConflictError(f"A watchlist named '{name}' already exists") from None

    def delete_watchlist(self, owner: str, wl_id: int) -> None:
        with self.session() as s, s.begin():
            row = self._own(s, owner, wl_id)
            was_default = row.is_default
            s.delete(row)
            s.flush()
            if was_default:
                nxt = s.scalar(select(WatchlistRow).where(WatchlistRow.owner == owner).order_by(WatchlistRow.id).limit(1))
                if nxt:
                    nxt.is_default = True

    def add_watchlist_item(self, owner: str, wl_id: int, symbol: str) -> Watchlist:
        with self.session() as s, s.begin():
            row = self._own(s, owner, wl_id)
            iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
            if iid is None:
                raise NotFoundError(f"Unknown symbol '{symbol}'")
            count = s.scalar(select(func.count()).select_from(WatchlistItemRow).where(WatchlistItemRow.watchlist_id == wl_id)) or 0
            exists = s.scalar(select(WatchlistItemRow.instrument_id).where(WatchlistItemRow.watchlist_id == wl_id, WatchlistItemRow.instrument_id == iid))
            if exists is None:  # idempotent
                if count >= self.MAX_ITEMS:
                    raise LimitError(f"At most {self.MAX_ITEMS} symbols per watchlist")
                nxt = (s.scalar(select(func.max(WatchlistItemRow.position)).where(WatchlistItemRow.watchlist_id == wl_id)) or 0) + 1
                s.add(WatchlistItemRow(watchlist_id=wl_id, instrument_id=iid, position=nxt))
                s.flush()
            return self._wl(s, row)

    def remove_watchlist_item(self, owner: str, wl_id: int, symbol: str) -> Watchlist:
        with self.session() as s, s.begin():
            row = self._own(s, owner, wl_id)
            iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == symbol))
            res = s.execute(delete(WatchlistItemRow).where(WatchlistItemRow.watchlist_id == wl_id, WatchlistItemRow.instrument_id == iid))
            if res.rowcount == 0:
                raise NotFoundError(f"{symbol} is not in this watchlist")
            s.flush()
            return self._wl(s, row)

    def reorder_watchlist(self, owner: str, wl_id: int, symbols: list[str]) -> Watchlist:
        with self.session() as s, s.begin():
            row = self._own(s, owner, wl_id)
            if sorted(symbols) != sorted(self._symbols(s, wl_id)):
                raise ConflictError("Order must contain exactly the symbols currently in the watchlist")
            for pos, sym in enumerate(symbols, start=1):
                iid = s.scalar(select(InstrumentRow.id).where(InstrumentRow.symbol == sym))
                s.execute(update(WatchlistItemRow).where(WatchlistItemRow.watchlist_id == wl_id, WatchlistItemRow.instrument_id == iid).values(position=pos))
            s.flush()
            return self._wl(s, row)

    # saved screens ----------------------------------------------------
    MAX_SCREENS = 25

    @staticmethod
    def _sc(r: SavedScreenRow) -> SavedScreen:
        return SavedScreen(r.id, r.owner, r.name, dict(r.definition))

    def list_screens(self, owner: str) -> list[SavedScreen]:
        with self.session() as s:
            rows = s.scalars(select(SavedScreenRow).where(SavedScreenRow.owner == owner).order_by(SavedScreenRow.id)).all()
            return [self._sc(r) for r in rows]

    def create_screen(self, owner: str, name: str, definition: dict) -> SavedScreen:
        try:
            with self.session() as s, s.begin():
                n = s.scalar(select(func.count()).select_from(SavedScreenRow).where(SavedScreenRow.owner == owner)) or 0
                if n >= self.MAX_SCREENS:
                    raise LimitError(f"At most {self.MAX_SCREENS} saved screens")
                row = SavedScreenRow(owner=owner, name=name, definition=definition)
                s.add(row)
                s.flush()
                return self._sc(row)
        except IntegrityError:
            raise ConflictError(f"A screen named '{name}' already exists") from None

    def delete_screen(self, owner: str, screen_id: int) -> None:
        with self.session() as s, s.begin():
            res = s.execute(delete(SavedScreenRow).where(SavedScreenRow.id == screen_id, SavedScreenRow.owner == owner))
            if res.rowcount == 0:
                raise NotFoundError("Saved screen not found")

    # portfolios -------------------------------------------------------
    MAX_PORTFOLIOS = 10
    MAX_TXNS = 2000

    @staticmethod
    def _txn(r: PortfolioTxnRow) -> Txn:
        return Txn(r.id, r.portfolio_id, r.day, r.kind, r.symbol, r.quantity, r.price, r.fee, r.amount, r.note)

    @staticmethod
    def _txn_row(pid: int, t: Txn) -> PortfolioTxnRow:
        return PortfolioTxnRow(portfolio_id=pid, day=t.day, kind=t.kind, symbol=t.symbol, quantity=t.quantity,
                               price=t.price, fee=t.fee, amount=t.amount, note=t.note)

    def _own_portfolio(self, s: Session, owner: str, pid: int, lock: bool = False) -> PortfolioRow:
        q = select(PortfolioRow).where(PortfolioRow.id == pid, PortfolioRow.owner == owner)
        row = s.scalar(q.with_for_update() if lock else q)  # FOR UPDATE serialises concurrent ledger writes
        if row is None:
            raise NotFoundError("Portfolio not found")
        return row

    def list_portfolios(self, owner: str) -> list[Portfolio]:
        with self.session() as s:
            rows = s.scalars(select(PortfolioRow).where(PortfolioRow.owner == owner).order_by(PortfolioRow.id)).all()
            return [Portfolio(r.id, r.owner, r.name) for r in rows]

    def create_portfolio(self, owner: str, name: str, initial: Txn | None = None) -> Portfolio:
        try:
            with self.session() as s, s.begin():
                n = s.scalar(select(func.count()).select_from(PortfolioRow).where(PortfolioRow.owner == owner)) or 0
                if n >= self.MAX_PORTFOLIOS:
                    raise LimitError(f"At most {self.MAX_PORTFOLIOS} portfolios")
                row = PortfolioRow(owner=owner, name=name)
                s.add(row)
                s.flush()
                if initial is not None:
                    s.add(self._txn_row(row.id, initial))
                return Portfolio(row.id, owner, name)
        except IntegrityError:
            raise ConflictError(f"A portfolio named '{name}' already exists") from None

    def get_portfolio(self, owner: str, pid: int) -> Portfolio:
        with self.session() as s:
            r = self._own_portfolio(s, owner, pid)
            return Portfolio(r.id, r.owner, r.name)

    def delete_portfolio(self, owner: str, pid: int) -> None:
        with self.session() as s, s.begin():
            self._own_portfolio(s, owner, pid)
            s.execute(delete(PortfolioRow).where(PortfolioRow.id == pid))

    def _load_txns(self, s: Session, pid: int) -> list[Txn]:
        rows = s.scalars(select(PortfolioTxnRow).where(PortfolioTxnRow.portfolio_id == pid).order_by(PortfolioTxnRow.id)).all()
        return [self._txn(r) for r in rows]

    def list_txns(self, owner: str, pid: int) -> list[Txn]:
        with self.session() as s:
            self._own_portfolio(s, owner, pid)
            return self._load_txns(s, pid)

    def add_txn(self, owner: str, pid: int, txn: Txn, validate) -> Txn:
        with self.session() as s, s.begin():
            self._own_portfolio(s, owner, pid, lock=True)
            existing = self._load_txns(s, pid)
            if len(existing) >= self.MAX_TXNS:
                raise LimitError(f"At most {self.MAX_TXNS} transactions per portfolio")
            validate([*existing, txn])  # raises -> the transaction rolls back, nothing is stored
            row = self._txn_row(pid, txn)
            s.add(row)
            s.flush()
            return self._txn(row)

    def delete_txn(self, owner: str, pid: int, txn_id: int, validate) -> None:
        with self.session() as s, s.begin():
            self._own_portfolio(s, owner, pid, lock=True)
            existing = self._load_txns(s, pid)
            rest = [t for t in existing if t.id != txn_id]
            if len(rest) == len(existing):
                raise NotFoundError("Transaction not found")
            validate(rest)
            s.execute(delete(PortfolioTxnRow).where(PortfolioTxnRow.id == txn_id, PortfolioTxnRow.portfolio_id == pid))

    # alerts -----------------------------------------------------------
    MAX_ALERTS = 50
    MAX_EVENTS = 500
    _ALERT_FIELDS = ("symbol", "kind", "threshold", "window", "cooldown_days", "enabled", "note", "last_observed_day",
                     "last_condition", "fired_in_episode", "last_fired_day", "created_day")

    @staticmethod
    def _alert(r: AlertRow) -> Alert:
        return Alert(r.id, r.owner, r.symbol, r.kind, r.threshold, r.window, r.cooldown_days, r.enabled, r.note,
                     r.last_observed_day, r.last_condition, r.fired_in_episode, r.last_fired_day, r.created_day)

    def _own_alert(self, s: Session, owner: str, alert_id: int) -> AlertRow:
        r = s.scalar(select(AlertRow).where(AlertRow.id == alert_id, AlertRow.owner == owner))
        if r is None:
            raise NotFoundError("Alert not found")
        return r

    def list_alerts(self, owner: str) -> list[Alert]:
        with self.session() as s:
            return [self._alert(r) for r in s.scalars(select(AlertRow).where(AlertRow.owner == owner).order_by(AlertRow.id))]

    def create_alert(self, owner: str, alert: Alert) -> Alert:
        with self.session() as s, s.begin():
            n = s.scalar(select(func.count()).select_from(AlertRow).where(AlertRow.owner == owner)) or 0
            if n >= self.MAX_ALERTS:
                raise LimitError(f"At most {self.MAX_ALERTS} alerts")
            row = AlertRow(owner=owner, **{k: getattr(alert, k) for k in self._ALERT_FIELDS})
            s.add(row)
            s.flush()
            return self._alert(row)

    def get_alert(self, owner: str, alert_id: int) -> Alert:
        with self.session() as s:
            return self._alert(self._own_alert(s, owner, alert_id))

    def update_alert(self, owner: str, alert_id: int, fields: dict) -> Alert:
        with self.session() as s, s.begin():
            r = self._own_alert(s, owner, alert_id)
            for k, v in fields.items():
                if k not in self._ALERT_FIELDS:
                    raise ValueError(f"cannot update {k}")
                setattr(r, k, v)
            s.flush()
            return self._alert(r)

    def delete_alert(self, owner: str, alert_id: int) -> None:
        with self.session() as s, s.begin():
            self._own_alert(s, owner, alert_id)
            s.execute(delete(AlertRow).where(AlertRow.id == alert_id))

    def list_enabled_alerts(self) -> list[Alert]:
        with self.session() as s:
            return [self._alert(r) for r in s.scalars(select(AlertRow).where(AlertRow.enabled.is_(True)).order_by(AlertRow.id))]

    def record_evaluation(self, alert_id: int, expected_last_observed_day, ev, now: datetime) -> bool:
        """Compare-and-set on last_observed_day inside one transaction, so two evaluators cannot both fire."""
        with self.session() as s, s.begin():
            r = s.scalar(select(AlertRow).where(AlertRow.id == alert_id).with_for_update())
            if r is None or not r.enabled or r.last_observed_day != expected_last_observed_day:
                return False
            r.last_observed_day, r.last_condition = ev.last_observed_day, ev.last_condition
            r.fired_in_episode, r.last_fired_day = ev.fired_in_episode, ev.last_fired_day
            for e in ev.events:
                s.add(AlertEventRow(alert_id=r.id, owner=r.owner, symbol=r.symbol, kind=r.kind, observed_day=e["observed_day"],
                                    observed_value=e["observed_value"], threshold=r.threshold, message=e["message"], evaluated_at=now))
            s.flush()
            keep = s.scalars(select(AlertEventRow.id).where(AlertEventRow.owner == r.owner).order_by(AlertEventRow.id.desc()).limit(self.MAX_EVENTS)).all()
            if len(keep) == self.MAX_EVENTS:
                s.execute(delete(AlertEventRow).where(AlertEventRow.owner == r.owner, AlertEventRow.id < min(keep)))
            return True

    def list_events(self, owner: str, alert_id: int | None = None, limit: int = 50, unread_only: bool = False) -> list[AlertEvent]:
        with self.session() as s:
            q = select(AlertEventRow).where(AlertEventRow.owner == owner)
            if alert_id is not None:
                q = q.where(AlertEventRow.alert_id == alert_id)
            if unread_only:
                q = q.where(AlertEventRow.read.is_(False))
            return [AlertEvent(r.id, r.alert_id, r.owner, r.symbol, r.kind, r.observed_day, r.observed_value, r.threshold,
                               r.message, r.evaluated_at, r.read) for r in s.scalars(q.order_by(AlertEventRow.id.desc()).limit(limit))]

    def unread_count(self, owner: str) -> int:
        with self.session() as s:
            return s.scalar(select(func.count()).select_from(AlertEventRow).where(AlertEventRow.owner == owner, AlertEventRow.read.is_(False))) or 0

    def mark_events_read(self, owner: str, ids: list[int] | None) -> int:
        with self.session() as s, s.begin():
            q = update(AlertEventRow).where(AlertEventRow.owner == owner, AlertEventRow.read.is_(False))
            if ids is not None:
                q = q.where(AlertEventRow.id.in_(ids))
            return s.execute(q.values(read=True)).rowcount
