# MarketPulse — Market intelligence, engineered.

A stock market intelligence platform: FastAPI data backend, deterministic mock provider, and a dark, information-dense Next.js workstation UI. Built in 7 parts; see `PROGRESS.md`.

> **Demo mode:** by default all prices are *synthetic* (seeded random walk). They are labeled "Simulated" in the UI and API (`meta.data_class`). Index cards use ETFs (SPY, QQQ, DIA, IWM) as labeled proxies.

## Status — Part 1 of 7

```
[███░░░░░░░░░░░░░░░░░░░░░░░░░░░] 14%  (1/7 parts)
```

Included now: monorepo, config + JSON logging, provider abstraction, mock provider, `/health` `/ready`, `/api/v1/stocks*`, `/api/v1/market/overview`, design system (dark/light tokens), collapsible sidebar + mobile drawer, Ctrl/Cmd+K command palette, dashboard, markets table, symbol page with interactive SVG chart (area/line/candles, SMA, crosshair), settings, Docker Compose.

Not yet built: database persistence/migrations, ingestion pipeline, indicators beyond the chart's SMA overlay, auth, and everything marked "Ships in Part N" in the UI.

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

The build sandbox used for Part 1 had no access to PyPI or npm, so:
- ✅ Mock provider verified by running it (determinism, valid OHLC for all 16 symbols); backend byte-compiles.
- ⚠️ `pytest`, `ruff`, `npm install`, `tsc`, `next build` and the UI were **not executed** here. Run `make test` and `make lint`, and `cd frontend && npm install && npm run typecheck && npm run build` on your machine; send me any errors and I'll fix them in the next part.

## Layout
`backend/` FastAPI app · `frontend/` Next.js (App Router, Tailwind 3) · `docs/` · `.github/workflows/ci.yml`
