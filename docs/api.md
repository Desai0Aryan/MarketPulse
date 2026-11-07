# API (through Part 2)  — interactive docs at `/docs`

Reads: `GET /health`, `GET /ready` (503 if DB/provider down), `GET /api/v1/stocks`, `/stocks/{symbol}`, `/stocks/{symbol}/latest`, `/stocks/{symbol}/prices?range=|start=&end=&limit=`, `/stocks/{symbol}/indicators`, `/market/overview`, `/pipeline/status`, `/pipeline/runs?status=&limit=&offset=`, `/pipeline/runs/{id}`, `/pipeline/quality`.

Writes (guarded, return 202 + `run_id`; 409 if a job is running; 422 for bad symbols/dates): `POST /api/v1/pipeline/ingest {symbols?, mode: incremental|reindex}`, `POST /api/v1/pipeline/backfill {symbols, start, end?}`.

Every market response carries `meta.data_class` (`simulated` in demo mode). Errors are `{ "detail": "..." }`; unknown symbol → 404; no stored data yet → 409.

CLI: `python -m app.cli seed | backfill SYMBOL --start D [--end D] | ingest | reindex | worker`.

## Added in Part 3

`GET /api/v1/search?q=&limit=` ranked symbol/company search.
`GET /api/v1/stocks/{symbol}/technicals?range=&sma=20,50,200&ema=12,26&rsi=14&macd=12,26,9&bb_window=20&bb_k=2&atr=14` parameterised indicators (422 on invalid parameters; formulas returned in the response).
`GET /api/v1/stocks/{symbol}/returns?range=` return/risk statistics and cumulative-return and drawdown series.
`GET /api/v1/stocks/{symbol}/prices.csv?range=` CSV export (<= 5000 rows, `#`-prefixed metadata lines, text cells protected against formula injection).
Watchlists (owner-scoped; the "demo" owner until authentication): `GET|POST /watchlists`, `PATCH|DELETE /watchlists/{id}`, `POST /watchlists/{id}/items`, `DELETE /watchlists/{id}/items/{symbol}`, `PUT /watchlists/{id}/order`.
Errors: 404 unknown/foreign watchlist or symbol, 409 duplicate name or invalid reorder, 422 invalid input or limit (20 lists, 100 symbols each).

## Part 4: Screener & Compare

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/screener/fields` | Metric catalogue (key, label, unit, definition) and limits |
| POST | `/api/v1/screener/query` | Body: `filters[]` (`field`, `op` in gt/gte/lt/lte/between/eq, `value`, `value2`), `kind`, `sort`, `descending`, `page`, `page_size` (≤100). 422 on unknown field/op, non-finite value, reversed range, > 12 filters |
| POST | `/api/v1/screener/export.csv` | Same body; first 100 matches (bounded); `#` metadata lines; formula-injection safe |
| GET/POST | `/api/v1/screener/saved` | Owner-scoped saved screens (max 25, unique name per owner, definition validated before storing) |
| DELETE | `/api/v1/screener/saved/{id}` | 404 if missing or owned by someone else |
| POST | `/api/v1/compare` | Body: `symbols` (2-10 distinct), `range`, optional `rolling_pair`, `rolling_window` (10-250). Response: rebased series, per-symbol stats, correlation matrix, coverage, notes |
| POST | `/api/v1/compare/export.csv` | Rebased series for the aligned window |

**Metric definitions.** Computed server-side from stored bars at each instrument's latest session, using only data up to that session. `rel_volume` = latest volume / mean of the prior 30 sessions. `rsi14` = Wilder RSI on adjusted closes. `volatility_20d` = sample std of the last 20 daily returns × √252. 52-week distances use unadjusted highs/lows over 365 calendar days. A metric that cannot be computed is `null` and a filter on it never matches (never treated as 0).

**Compare alignment.** Inner join on trading days present for every selected symbol; nothing is forward-filled. Dropped days per symbol are reported in `coverage`. Correlation is Pearson on daily simple returns of adjusted closes; constant series give `null`, not 0. Rolling correlation at day *t* uses only the trailing window ending at *t*.
