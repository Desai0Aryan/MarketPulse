.PHONY: dev stop test lint backend frontend migrate seed backfill ingest reindex benchmark test-pg

# Full stack in Docker (Postgres + migrate + API + worker + web)
dev:
	docker compose up --build

stop:
	docker compose down

# Local, no Docker: run in two terminals (in-memory storage, demo data auto-seeded)
backend:
	cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

test:
	cd backend && python -m pytest -q

# Needs a disposable PostgreSQL: make test-pg URL=postgresql+psycopg://user:pw@localhost:5432/marketpulse_test
test-pg:
	cd backend && MP_TEST_DATABASE_URL=$(URL) python -m pytest -q tests/test_sql_repo.py

lint:
	cd backend && ruff check .
	cd frontend && npm run typecheck && npm run lint

# Database / pipeline commands (use MP_STORAGE=postgres and MP_DATABASE_URL for a real database)
migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.cli seed

# make backfill SYMBOL=NVDA START=2025-01-01
backfill:
	cd backend && python -m app.cli backfill $(SYMBOL) --start $(START)

ingest:
	cd backend && python -m app.cli ingest

reindex:
	cd backend && python -m app.cli reindex

benchmark:
	python scripts/benchmark.py
