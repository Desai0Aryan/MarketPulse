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
