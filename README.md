# OpenClip

Self-hosted, open-source AI video repurposing — long-form → Shorts.

Independent project. Not affiliated with Opus Clip.

## Status

**Phases 0–9 implemented.** End-to-end pipeline verified with a playable **1080×1920** MP4.

## Hardware

Designed for **8 GB VRAM / 16 GB RAM**. Only one heavyweight model on GPU at a time (`MAX_CONCURRENT_GPU_JOBS=1`).

## Stack

- React + TypeScript + Vite + Tailwind
- FastAPI + SQLAlchemy + PostgreSQL + Redis + Celery
- faster-whisper (WhisperX/pyannote optional), Ollama Qwen ranking, OpenCV crop, FFmpeg render

No paid AI APIs required for the core path.

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres redis

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# other terminal
uv run celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency=1 --pool=solo

# frontend
cd frontend
npm install
npm run dev
```

Optional Ollama ranking:

```bash
ollama pull qwen3:4b
```

Whisper: set `WHISPER_MODEL=tiny` for quick tests, `large-v3` for quality (needs more VRAM/time).

## First Short (E2E)

```bash
# generates synthetic speech sample + runs full pipeline
uv run --project backend python scripts/e2e_pipeline.py
```

Or via UI: create project → upload → Process → Shorts → download.

## Docs

See `docs/` for architecture, models/licenses, GPU setup, API, troubleshooting.

## Limitations

- OpenCV 5 on some installs lacks Haar cascades → center-crop fallback
- pyannote / WhisperX are optional (HF token / extra deps)
- Qwen ranking falls back to deterministic scores if Ollama is down
- NVIDIA driver must be healthy for GPU acceleration
