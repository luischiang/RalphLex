.PHONY: dev dev-backend dev-frontend install lint test typecheck

dev-backend:
	.venv/bin/uvicorn backend.app:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

lint:
	.venv/bin/ruff check backend/ tests/
	.venv/bin/ruff format --check backend/ tests/

test:
	.venv/bin/pytest tests/ -v

typecheck:
	.venv/bin/mypy backend/
