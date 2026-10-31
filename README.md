# MarketPulse — Market intelligence, engineered.

A stock market intelligence platform: FastAPI data backend, deterministic mock provider, and a dark, information-dense Next.js workstation UI. Built in 7 parts; see `PROGRESS.md`.

> **Demo mode:** by default all prices are *synthetic* (seeded random walk). They are labeled "Simulated" in the UI and API (`meta.data_class`). Index cards use ETFs (SPY, QQQ, DIA, IWM) as labeled proxies.

## Status — Part 2 of 7

```
[█████████░░░░░░░░░░░░░░░░░░░░░] 29%  (2/7 parts)
```

Part 2 adds: ingestion pipeline (retry/backoff/rate limit, validation with stored rejections, idempotent upserts, forward-only checkpoints, historical-correction handling), indicator engine (SMA/EMA/RSI/MACD/Bollinger/ATR/ROC/volatility, drawdown) with no-look-ahead tests, PostgreSQL schema + Alembic migration, SQL + in-memory repositories, pipeline API, CLI (`seed/backfill/ingest/reindex/worker`), scheduler worker, quality report, benchmark script, and a working **Data Pipeline** page.

Part 1 included: monorepo, config + JSON logging, provider abstraction, mock provider, `/health` `/ready`, `/api/v1/stocks*`, `/api/v1/market/overview`, design system (dark/light tokens), collapsible sidebar + mobile drawer, Ctrl/Cmd+K command palette, dashboard, markets table, symbol page with interactive SVG chart (area/line/candles, SMA, crosshair), settings, Docker Compose.

Not yet built: indicator panels/charts in the UI (Part 3), watchlists/alerts/portfolio persistence, auth, and everything marked "Ships in Part N".

## Run it

**Docker**
```bash
cp .env.example .env
docker compose up --build        # web: http://localhost:3000  api: http://localhost:8000/docs
```

**Without Docker** (two terminals)
```bash
cd backend  && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev       # http://localhost:3000
```
The frontend proxies `/api/*` to `http://localhost:8000` (override with `API_INTERNAL_URL`).

## Verification status (honest)

The build sandbox had no access to PyPI or npm, and no PostgreSQL. Verified by actually running:
- ✅ 37 backend tests pass (indicators, validation, ingestion, retries, corrections, idempotency, checkpoints, job locking, quality report), run with a throwaway settings shim because `pydantic-settings` could not be installed.
- ✅ `python -m app.cli seed` ingested 20,800 bars for 16 symbols with 0 rejections; `scripts/benchmark.py` ran (numbers are printed by the script, not copied here).
- ⏭️ **Skipped, not run:** FastAPI endpoint tests (`tests/test_api.py`, FastAPI not installable here), PostgreSQL tests (`tests/test_sql_repo.py`, needs `MP_TEST_DATABASE_URL`), `ruff`, `npm install`, `tsc`, `next build`, and the UI. `app/storage/sql.py`, the Alembic migration, and all frontend code are unexecuted.

On your machine: `make test`, `make test-pg URL=...`, `make lint`, `cd frontend && npm install && npm run build`. Send me failures and I'll fix them.

## Layout
`backend/` FastAPI app · `frontend/` Next.js (App Router, Tailwind 3) · `docs/` · `.github/workflows/ci.yml`
