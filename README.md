# MarketPulse — Market intelligence, engineered.

A stock market intelligence platform: FastAPI data backend, deterministic mock provider, and a dark, information-dense Next.js workstation UI. Built in 7 parts; see `PROGRESS.md`.

> **Demo mode:** by default all prices are *synthetic* (seeded random walk). They are labeled "Simulated" in the UI and API (`meta.data_class`). Index cards use ETFs (SPY, QQQ, DIA, IWM) as labeled proxies.

## Status — Part 3 of 7

```
[█████████████░░░░░░░░░░░░░░░░░] 43%  (3/7 parts)
```

Part 3 adds: stock terminal tabs (Overview, Technicals, Returns, Data quality, News & financials placeholder), indicator overlays (SMA/EMA/Bollinger) with linked RSI and MACD panels and user-adjustable, server-validated parameters, return/risk statistics (annualised volatility, max drawdown, best/worst day, cumulative return and drawdown charts), ranked symbol search, **server-persisted watchlists** (multiple lists, rename, default, reorder, per-owner isolation) with a full Watchlists page, and safe CSV export.

Part 2 added: ingestion pipeline (retry/backoff/rate limit, validation with stored rejections, idempotent upserts, forward-only checkpoints, historical-correction handling), indicator engine (SMA/EMA/RSI/MACD/Bollinger/ATR/ROC/volatility, drawdown) with no-look-ahead tests, PostgreSQL schema + Alembic migration, SQL + in-memory repositories, pipeline API, CLI (`seed/backfill/ingest/reindex/worker`), scheduler worker, quality report, benchmark script, and a working **Data Pipeline** page.

Part 1 included: monorepo, config + JSON logging, provider abstraction, mock provider, `/health` `/ready`, `/api/v1/stocks*`, `/api/v1/market/overview`, design system (dark/light tokens), collapsible sidebar + mobile drawer, Ctrl/Cmd+K command palette, dashboard, markets table, symbol page with interactive SVG chart (area/line/candles, SMA, crosshair), settings, Docker Compose.

Not yet built: screener/compare (Part 4), alerts/portfolio (Part 5), backtests/news/AI/live updates (Part 6), authentication (watchlists use a shared "demo" profile), and everything marked "Ships in Part N". Charts are a custom SVG component rather than TradingView Lightweight Charts (no zoom/pan or image export yet); the library could not be installed or verified in the build sandbox.

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
- ✅ 64 backend tests pass: indicators (incl. no-look-ahead), validation, ingestion/retries/corrections/idempotency, checkpoints, job locking, quality report, **watchlist semantics and owner isolation, search ranking, CSV injection protection, return/risk statistics, parameterised technicals**. Run with a throwaway settings shim because `pydantic-settings` could not be installed.
- ✅ `python -m app.cli seed` ingested 20,800 bars for 16 symbols with 0 rejections.
- ⏭️ **Skipped, not run:** all FastAPI route tests (`tests/test_api.py`, FastAPI not installable here, so the new routers `watchlists.py`, `search.py` and the added `stocks.py` routes have never been executed), PostgreSQL tests (`tests/test_sql_repo.py`, needs `MP_TEST_DATABASE_URL`), `ruff`, `npm install`, `tsc`, `next build`, and the UI. `app/storage/sql.py`, both Alembic migrations and all frontend code are unexecuted.

On your machine: `make test`, `make test-pg URL=...`, `make lint`, `cd frontend && npm install && npm run build`. Send me failures and I'll fix them.

## Layout
`backend/` FastAPI app · `frontend/` Next.js (App Router, Tailwind 3) · `docs/` · `.github/workflows/ci.yml`
