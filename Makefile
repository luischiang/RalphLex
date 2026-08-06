.PHONY: dev dev-backend dev-frontend install test lint

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

dev-backend:
	.venv/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev -- --port 3000

dev:
	$(MAKE) -j2 dev-backend dev-frontend

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check backend tests
	cd frontend && npm run lint
