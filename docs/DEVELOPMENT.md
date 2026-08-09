# Development

## Prerequisites

- Python 3.11+ (uv recommended)
- Docker (PostgreSQL 16, Redis 7)
- FFmpeg (Phase 2+)
- NVIDIA drivers / CUDA optional for Phase 1

## Backend

```bash
cp .env.example .env
docker compose up -d postgres redis
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Worker:

```bash
cd backend
uv run celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency=1
```

Tests:

```bash
cd backend
uv run pytest -q
```

## Phase rule

Finish and verify the current phase before starting the next. No placeholder AI.
