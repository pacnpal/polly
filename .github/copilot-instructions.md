# Copilot Instructions for Polly

Polly is a Discord poll bot with a FastAPI + HTMX web interface. These instructions guide GitHub Copilot when generating code, reviewing PRs, and acting as a coding agent in this repository.

## Tech Stack

- **Language**: Python 3.11+
- **Backend**: FastAPI, discord.py, APScheduler
- **Database**: SQLAlchemy 2.x with SQLite (aiosqlite)
- **Cache/Queue**: Redis
- **Frontend**: Jinja2 templates, Bootstrap 5, HTMX (no JavaScript framework)
- **Auth**: Discord OAuth2 + JWT (python-jose)
- **Package management**: `uv` (not pip/poetry)
- **Testing**: pytest with `pytest-asyncio` (asyncio_mode = auto), `pytest-cov` (≥80% coverage required)
- **Linting/formatting**: ruff
- **Container**: Docker + docker-compose

## Common Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run the app
uv run python -m polly.main
uv run uvicorn polly.main:app --reload

# Tests
uv run pytest
uv run pytest -m "not slow"          # skip slow tests
uv run pytest tests/test_foo.py::test_bar

# Lint / format
uv run ruff check .
uv run ruff format .
```

## Repository Layout

- `polly/` — main package (entry point: `polly.main`)
- `templates/` — Jinja2 + HTMX templates; `templates/htmx/` for partials
- `static/` — static assets and `static/uploads/` for poll images
- `tests/` — pytest suite; markers: `slow`, `integration`, `unit`, `security`, `performance`, `edge_case`, `malicious`
- `cli/`, `scripts/` — operational scripts
- `nginx/`, `Dockerfile`, `docker-compose*.yml` — deployment
- `memory-bank/` — project context docs

## Coding Conventions

- **HTMX-first frontend**: do not introduce React, Vue, or client-side JS frameworks. Server-rendered partials returned from FastAPI endpoints, swapped via `hx-*` attributes.
- **Async by default** for FastAPI route handlers and discord.py callbacks. Use `aiosqlite`/SQLAlchemy async sessions for DB access where the surrounding code already does.
- **Timezone awareness**: poll scheduling is timezone-aware (default `US/Eastern`). Always use timezone-aware `datetime` objects; store UTC, render in user's tz with `pytz`.
- **Admin-only operations**: poll creation/management requires Discord server admin permissions; preserve the existing auth checks.
- **Secrets** come from environment variables (`.env` / `python-decouple`). Never hardcode tokens, client secrets, or `SECRET_KEY`. See `.env.example` for the full list.
- **Image uploads**: full-size images, validated with `python-magic` and `Pillow`; cleanup is automatic on poll deletion — preserve this behavior.
- **Logging over print**: use the standard `logging` module; pytest is configured to surface INFO logs.

## Testing Expectations

- New features need tests. Coverage gate is 80% (`--cov-fail-under=80` in `pytest.ini`).
- Use the appropriate marker (`unit`, `integration`, `security`, etc.) so test selection works.
- Async tests do not need an explicit `@pytest.mark.asyncio` decorator (`asyncio_mode = auto`).
- Mock Discord/Redis/network calls with `pytest-mock` rather than hitting real services.

## What to Avoid

- Adding new top-level dependencies without a clear justification — prefer the libraries already in `pyproject.toml`.
- Switching package managers, build backends, or test runners.
- Introducing client-side JavaScript frameworks or build steps for the frontend.
- Schema changes that silently break existing SQLite databases — provide a migration path (`migrate_database.py` / `run_migration.py` are the existing patterns).
- Disabling coverage, ruff, or test markers to make CI green.

## PR / Commit Style

- Keep commits focused; match the surgical-change ethos in `CLAUDE.md` at the repo root.
- Reference issues when applicable.
- Ensure `uv run ruff check .` and `uv run pytest` pass locally before pushing.
