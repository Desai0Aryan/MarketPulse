.PHONY: dev stop test lint backend frontend

# Full stack in Docker (Postgres + API + web)
dev:
	docker compose up --build

stop:
	docker compose down

# Local, no Docker: run in two terminals
backend:
	cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check .
	cd frontend && npm run typecheck && npm run lint

# Added in later parts: migrate, seed, backfill, benchmark
