# RalphLex

Autonomous multi-agent legal reasoning system. See `SYSTEMGOAL.md` for the product spec and `scripts/ralph/prd.json` for the user story backlog.

## Backend

- Python venv lives at `.venv/` (created via `python3 -m venv .venv`). Install with `.venv/bin/pip install -e ".[dev]"`.
- FastAPI app entrypoint: `backend/main.py` (`app` object). Run with `.venv/bin/uvicorn backend.main:app --reload --port 8000`.
- All API routes are mounted under `/api/...`.
- Lint with `ruff check backend tests`. Tests run with `.venv/bin/pytest` (config in `pyproject.toml`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`).
- `Makefile` has `dev-backend`, `dev-frontend`, `dev` (runs both via `make -j2`), `install`, `test`, `lint` targets.

## Frontend

- `frontend/` is a Vite + React + TypeScript app, Tailwind CSS v4 (via `@tailwindcss/vite` plugin, no `postcss.config`/`tailwind.config` needed — `src/index.css` just has `@import "tailwindcss";`).
- Dev server runs on port 3000 (`npm run dev -- --port 3000`); `vite.config.ts` proxies `/api/*` to `http://localhost:8000`.
- Lint: `npm run lint` (oxlint). Build: `npm run build` (`tsc -b && vite build`).

## Case data

- Case working directories live under `data/cases/{case_id}/` (gitignored except `.gitkeep`) — see RLEX-002+ for the folder structure (`config/`, `state/`, `iterations/`, `outputs/`).

## Environment agent notes

- The sandboxed Bash tool's shell state (cwd) does not persist into commands backgrounded with a trailing `&`— background dev servers were killed unexpectedly when chaining `cd` + `&` in one command. Use the Bash tool's own `run_in_background: true` parameter to start long-running servers (uvicorn, vite dev) instead of shell `&`/`nohup`, and stop them with `TaskStop`.
