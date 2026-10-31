# Database design (Part 2)

| Table | Key | Notes |
|---|---|---|
| `instruments` | `id`, unique `symbol` | `kind` = equity \| index_proxy |
| `prices` | PK `(instrument_id, interval, day)` | NUMERIC(18,4); CHECK `high>=low AND low>0 AND volume>=0`; index on `day` |
| `indicators` | PK `(instrument_id, day)` | one column per indicator, NULL = not enough history |
| `ingestion_runs` | `id` | `stats`/`events`/`params` are JSONB (flexible per-run metrics, not time series) |
| `ingestion_checkpoints` | PK `instrument_id` | forward-only `last_day` |
| `rejected_records` | `id` | FK to run (cascade); `raw` JSONB keeps the offending record |

Time series live in relational columns, not JSONB. The composite primary key doubles as the read index for `(instrument, interval, day range)`; `ix_prices_day` serves cross-sectional queries (screener, movers, Part 4). Deleting an instrument cascades to its prices/indicators/checkpoint; deleting a run keeps its prices (`run_id` set NULL) but removes its rejections.

## Query plans

Plans depend on your data and PostgreSQL version, so none are pasted here. To inspect the main read path against a seeded database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT day, open, high, low, close, adj_close, volume
FROM prices
WHERE instrument_id = (SELECT id FROM instruments WHERE symbol = 'AAPL')
  AND interval = '1d' AND day BETWEEN '2026-01-01' AND '2026-10-23'
ORDER BY day;
-- expect an Index Scan / Index Only Scan using prices_pkey

EXPLAIN (ANALYZE, BUFFERS)
SELECT instrument_id, max(day) FROM prices GROUP BY instrument_id;
```

## Migrations
`cd backend && alembic upgrade head` (docker-compose runs this in the `migrate` service before the API starts). Migration `0001` is hand-written to match `app/database/models.py`; `tests/test_sql_repo.py` applies it and exercises the repository.
