# Repository Guidelines

## Project Structure & Module Organization
- `api/` holds the FastAPI backend (`api/main.py`, `api/routes/`, trading helpers) that serves indicators, scans, and WebSocket signals on port 8000.
- `dashboard/` is the Next.js 13 app directory (`app/`, `components/`, `lib/`) powering the React dashboard on port 3000; treat it as a separate npm workspace (see `dashboard/package.json`).
- `tests/` contains `pytest` suites that mirror production modules (`test_routes_portfolio.py`, `test_models.py`, etc.). Keep new backend tests adjacent to the modules they exercise.
- `docs/` archives plans and reference notes. Scripts live under `scripts/`, and legacy utilities (e.g., `nalgoV2*.py`) stay in the root for historical context.

## Build, Test, and Development Commands
- Create the Python virtualenv once: `python3.12 -m venv venv && source venv/bin/activate`, then `pip install -r requirements.txt`.
- Copy templates before running: `cp .env.example .env` and `cp dashboard/.env.example dashboard/.env`.
- Start the API with hot reload: `python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000`.
- Install/dashboard dependencies: `cd dashboard && npm install`, then `npm run dev` to serve on `localhost:3000` (use `npm run build` before deploying).
- Run the full test suite via `pytest tests/` from the repo root after activating the virtualenv.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, `snake_case` for functions/variables, and descriptive module names under `api/`.
- React components and hooks follow PascalCase (e.g., `LiveTicker`) with camelCase props/state; keep shared utilities in `dashboard/lib/`.
- Environment variables stay UPPER_SNAKE_CASE; avoid committing secrets (`EXCHANGE_API_KEY`, `MONGODB_URI`, etc.).
- Prefer inline comments for trading logic clarity rather than terse hashes, and keep TODOs actionable (e.g., “TODO: refactor scan scheduler”).

## Testing Guidelines
- Tests live in `tests/` and follow `test_<unit>.py` naming so pytest auto-discovers them.
- Focus on one layer per test file (models, risk, database, portfolio routes); use fixtures in `tests/__init__.py` when repeated state is needed.
- Run `pytest tests/` after code changes, especially when touching `api/` routes or database helpers. Reference logs in `./.pytest_cache/` when diagnosing failures.

## Commit & Pull Request Guidelines
- Follow the conventional commit style seen in recent history (e.g., `fix: ...`, `feat: ...`, `chore: ...`); keep the subject under 72 characters.
- Pull requests should summarize changes, list testing steps, and link to relevant issues or docs. Attach screen recordings/screenshots when dashboard UI changes occur.
- Tag reviewers for the backend versus frontend depending on touched directories, and rebase onto `main` before merging to keep history linear.

## Security & Configuration Tips
- Never commit `.env` or `dashboard/.env`; this repo already includes `.env.example` templates.
- Paper trading defaults (`PAPER_TRADING=true`) protect funds—enable real trading only after reviewing `api/trading_engine.py`.
- Store Mongo/CCXT secrets in a secured vault and reference them through the environment during CI or deployment rather than hardcoding.
