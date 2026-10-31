"""PostgreSQL repository (SQLAlchemy 2.0 + psycopg3).

NOTE: written against the documented SQLAlchemy 2.0 API but NOT executed in the Part 2 build
sandbox (no package access). Run the integration tests in tests/test_sql_repo.py against a
real PostgreSQL (`MP_TEST_DATABASE_URL=...`) before relying on it.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    CheckpointRow, IndicatorRow, IngestionRunRow, InstrumentRow, PriceRow, RejectedRecordRow,
)
from app.domain import Checkpoint, Rejection, RunRecord, UpsertResult, utcnow
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
