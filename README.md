# OpenClip

Self-hosted, open-source AI video repurposing platform — long-form video → Shorts.

Independent implementation. Not affiliated with Opus Clip.

## Status

**Phase 0 + Phase 1 complete** — backend foundation only (no video AI yet).

| Phase | Status |
|-------|--------|
| 0 Architecture / repo bootstrap | Done |
| 1 Backend foundation | Done |
| 2 Media Agent | Pending |
| 3 Transcript Agent | Pending |
| 4–9 Clipping, ranking, edit, render, UI, E2E | Pending |

## Hardware requirements

Designed for:

- NVIDIA GPU with **8 GB VRAM**
- **16 GB** system RAM

GPU rule: only **one** heavyweight model (Whisper / Qwen / pyannote) on the GPU at a time.

## Stack

- Frontend (Phase 8): React + TypeScript + Vite + Tailwind
- Backend: FastAPI + Pydantic + SQLAlchemy + PostgreSQL
- Jobs: Celery + Redis
- Local LLM: Ollama (Qwen3-4B)
- Video: FFmpeg / FFprobe

No paid AI APIs required for the core path.

## Quick start (Phase 1)

```bash
# Infra
cp .env.example .env
docker compose up -d postgres redis

# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Worker (separate terminal)
cd backend
uv run celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency=1
```

Health: `GET http://localhost:8000/health`  
System: `GET http://localhost:8000/api/system/status`

## Model installation

See [docs/MODELS.md](docs/MODELS.md) and [docs/GPU_SETUP.md](docs/GPU_SETUP.md).  
Do not download large models until Phase 3+.

## Environment checks

```bash
python scripts/check_environment.py
python scripts/check_gpu.py
python scripts/check_ffmpeg.py
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Agents](docs/AGENTS.md)
- [Pipeline](docs/PIPELINE.md)
- [Models & licenses](docs/MODELS.md)
- [GPU setup](docs/GPU_SETUP.md)
- [Development](docs/DEVELOPMENT.md)
- [API](docs/API.md)
- [Database](docs/DATABASE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Licenses](docs/LICENSES.md)

## Limitations (current)

- No media upload / transcription / clip generation yet
- Frontend deferred to Phase 8
- Ollama / Whisper / pyannote not required until later phases
