# API (through Part 2)  — interactive docs at `/docs`

Reads: `GET /health`, `GET /ready` (503 if DB/provider down), `GET /api/v1/stocks`, `/stocks/{symbol}`, `/stocks/{symbol}/latest`, `/stocks/{symbol}/prices?range=|start=&end=&limit=`, `/stocks/{symbol}/indicators`, `/market/overview`, `/pipeline/status`, `/pipeline/runs?status=&limit=&offset=`, `/pipeline/runs/{id}`, `/pipeline/quality`.

Writes (guarded, return 202 + `run_id`; 409 if a job is running; 422 for bad symbols/dates): `POST /api/v1/pipeline/ingest {symbols?, mode: incremental|reindex}`, `POST /api/v1/pipeline/backfill {symbols, start, end?}`.

Every market response carries `meta.data_class` (`simulated` in demo mode). Errors are `{ "detail": "..." }`; unknown symbol → 404; no stored data yet → 409.

CLI: `python -m app.cli seed | backfill SYMBOL --start D [--end D] | ingest | reindex | worker`.
