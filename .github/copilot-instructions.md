# Copilot Cloud Agent Instructions — Polly

## Project Overview

Polly is a **Discord Poll Bot** with a **FastAPI web interface** for poll management. Users authenticate via Discord OAuth, create polls through the web dashboard or Discord slash commands, and votes are tracked in real time. The web UI uses **HTMX** (no JavaScript framework) with **Bootstrap 5** and **Jinja2** templates.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ (3.12 in CI) |
| Web framework | FastAPI (async, ASGI) |
| Discord | discord.py 2.4+ |
| ORM / DB | SQLAlchemy 2.0 + aiosqlite (SQLite) |
| Templates | Jinja2 + HTMX |
| CSS | Bootstrap 5 |
| Scheduling | APScheduler |
| Cache | Redis |
| Auth | Discord OAuth2 + JWT (python-jose) |
| Package manager | **uv** (not pip) |
| Build system | hatchling (pyproject.toml) |
| Linter | ruff |
| Test framework | pytest + pytest-asyncio + pytest-cov |

## Repository Layout

```
polly/                  # Main Python package (the app)
  main.py               # Entry point — initializes and runs the FastAPI app
  web_app.py            # FastAPI app factory, route registration, middleware
  database.py           # SQLAlchemy models: Poll, Vote, User, UserPreference, Guild, Channel
  auth.py               # Discord OAuth + JWT token management
  discord_bot.py        # Discord bot commands and event handlers
  validators.py         # PollValidator — central input validation/sanitization
  poll_operations.py    # Core poll CRUD business logic
  background_tasks.py   # APScheduler jobs (auto-open/close polls)
  security_middleware.py # Rate limiting + security headers middleware
  redis_client.py       # Async Redis connection wrapper
  services/             # Service layer (poll/, cache/, admin/ sub-packages)
  ...                   # ~59 modules total

templates/              # Jinja2 HTML templates
  htmx/                 # HTMX partial templates (fragments)
  index.html            # Landing page
  dashboard_htmx.html   # Main dashboard

static/                 # Frontend assets (JS, CSS, icons)
tests/                  # pytest test suite (~23 files)
cli/                    # CLI interface (poll, admin, system commands)
scripts/                # Deployment shell scripts
json/                   # Example poll JSON import files
memory-bank/            # Internal design docs/notes (.md)
deploy/                 # Deployment configs
nginx/                  # Nginx reverse proxy configs
```

## How to Set Up

### 1. Install dependencies

```bash
pip install uv          # if uv is not available
uv sync                 # installs all deps (including dev) into .venv
```

### 2. Environment variables

Copy `.env.example` → `.env` and fill in values. **Tests require a `.env` file to exist** (at minimum, copy the example as-is). Key variables:

- `DISCORD_TOKEN` — Discord bot token (required at import time by `polly.discord_bot`)
- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` — OAuth credentials
- `SECRET_KEY` — JWT signing key
- `REDIS_URL` / `REDIS_HOST` / `REDIS_PORT` — Redis connection (default port 6340)
- `DEBUG` — set `true` for debug logging

### 3. Database

SQLite auto-creates at `./db/polly.db`. Migrations run automatically via `uv run migrate_database.py` (also done in Docker entrypoint).

## Build & Run

```bash
# Run the app locally
uv run python -m polly.main

# Docker (production)
docker compose up -d          # starts Redis + Polly
docker compose -f docker-compose.dev.yml up -d   # dev mode with live reload

# Makefile shortcuts
make build    # build containers
make up       # start containers
make down     # stop containers
make status   # container status + recent logs
make health   # health check (curl /health + redis ping)
```

## Linting

```bash
uv run ruff check polly/
uv run ruff check polly/ --fix    # auto-fix safe issues
```

There is **no ruff config** in `pyproject.toml`; it uses defaults. As of the current codebase, `ruff check` reports ~38 pre-existing warnings (mostly unused imports in try/except blocks and unused variables). These are pre-existing and not introduced by your changes.

## Testing

```bash
# Run the full test suite
uv run pytest

# Run a specific test file
uv run pytest tests/test_database.py

# Run tests by marker
uv run pytest -m integration
uv run pytest -m security
```

### Test configuration (pytest.ini)

- `asyncio_mode = auto` — async tests run automatically
- `--cov=polly --cov-fail-under=80` — 80% minimum coverage enforced
- `--maxfail=10` — stops after 10 failures
- `--strict-markers` — only declared markers allowed

### Available markers

`slow`, `integration`, `unit`, `security`, `performance`, `edge_case`, `malicious`

### Known test issues and workarounds

> **IMPORTANT**: The test suite has several pre-existing failures you should be aware of:

1. **`tests/test_background_tasks.py`** — Fails to import: `cannot import name 'open_poll' from 'polly.background_tasks'`. The test references a function that was renamed/removed. **Workaround**: `--ignore=tests/test_background_tasks.py`

2. **`tests/test_discord_bot.py`** — Fails to import: `cannot import name 'create_quick_poll_command' from 'polly.discord_bot'`. **Workaround**: `--ignore=tests/test_discord_bot.py`

3. **`tests/test_web_app.py`** — Many tests fail because they reference module-level attributes (e.g., `web_app.get_polls_htmx`, `web_app.notify_error_async`) that no longer exist at that path (routes are registered via `add_*_routes()` functions internally). ~30+ failures in this file are pre-existing.

4. **`tests/test_database.py::TestTypeSafeColumn::test_get_datetime`** — Timezone-aware vs naive datetime comparison failure. Pre-existing.

5. **`tests/test_image_generator.py`** — Collection warning: `TestImageGenerator` has an `__init__` constructor, so pytest cannot collect it.

**To run only tests that pass**, use:
```bash
uv run pytest tests/ \
  --ignore=tests/test_background_tasks.py \
  --ignore=tests/test_discord_bot.py \
  -k "not test_get_datetime" \
  --no-cov
```
Note: `--no-cov` disables coverage checks, since ignoring files will lower coverage below the 80% threshold.

6. **`.env` required for test collection** — Without a `.env` file (or the env vars set), test collection fails with `UndefinedValueError: DISCORD_TOKEN not found`. Copy `.env.example` to `.env` before running tests.

## Architecture & Patterns

### App startup flow
`polly/main.py` → calls `create_app()` from `polly/web_app.py` → registers middleware stack → calls `add_core_routes(app)` → which calls `add_htmx_routes(app)`, loads Discord bot, etc.

### Middleware stack (applied in order)
1. `RateLimitMiddleware` — per-IP rate limiting (60/min, 1000/hr)
2. `SecurityHeadersMiddleware` — HSTS, X-Frame-Options, etc.
3. `EnhancedSecurityMiddleware` — advanced attack detection
4. `TurnstileSecurityMiddleware` — Cloudflare CAPTCHA
5. `AuthenticationMiddleware` — JWT/session validation

### Endpoint registration pattern
Each module exports an `add_*_routes(app)` function:
```python
def add_admin_routes(app: FastAPI):
    @app.get("/admin/...")
    async def handler(...): ...
```

### Service layer
Complex business logic lives in `polly/services/` (poll editing, opening, closing, caching, bulk operations). Endpoints call service functions.

### Validation pattern
All user input goes through `polly/validators.py` (`PollValidator` class with static methods like `validate_poll_name()`, `validate_options()`). Raises `ValidationError` on bad input.

### Database models
Defined in `polly/database.py`. JSON fields (e.g., poll options, emojis) are stored as JSON strings in the DB and accessed via `@property` getters/setters. `TypeSafeColumn` provides safe typed access to columns.

### Configuration
Uses `python-decouple` (`from decouple import config`). Pattern:
```python
VALUE = config("ENV_VAR", default="fallback", cast=int)
```

### Async everywhere
All I/O (database, HTTP, Discord API) uses async/await. Do not use blocking calls in async functions.

### Frontend (HTMX)
- Templates in `templates/`, partials in `templates/htmx/`
- Dynamic behavior via HTMX attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`)
- No JavaScript framework; vanilla JS in `static/` for form handling and uploads

### Error responses
API endpoints return JSON: `{"error": "description", "code": "error_code"}`

## Code Style & Conventions

- **Naming**: `async def get_*()` for retrieval, `validate_*()` for validation, `_private()` for internal
- **Classes**: PascalCase with role suffixes — `RateLimitMiddleware`, `PollEditService`, `ErrorHandler`
- **Imports**: stdlib → third-party → local. Many modules use try/except for optional imports with fallbacks.
- **No configured formatter**: ruff is the primary linting tool. No black/isort/mypy configuration exists in `pyproject.toml`.

## Docker & Deployment

- **Dockerfile**: `python:3.13-slim` base, installs via `uv sync --frozen`, runs as non-root `polly` user (UID 1000)
- **docker-compose.yml**: Redis (port 6340→6379) + Polly (port 8000, localhost only)
- **docker-entrypoint.sh**: runs migrations → `uv sync` → `uv run -m polly.main`
- **Makefile**: `make deploy`, `make update`, `make build`, `make up`, `make down`, `make logs`, `make status`, `make health`
- **systemd**: `polly.service` for non-Docker deployment
- **Nginx**: reverse proxy configs in `nginx/`
