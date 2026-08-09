# Architecture

OpenClip is a local-first video → Shorts pipeline.

```text
React UI (Phase 8+)
    ↓
FastAPI
    ↓
PostgreSQL + Redis
    ↓
Celery workers
    ↓
Media → Transcript → Clip Discovery → Editing → Render
    ↓
1080×1920 MP4
```

## Agents

1. **Media Agent** — ingest, validate, FFprobe, audio/proxy/thumbnails
2. **Transcript Agent** — Whisper / WhisperX / optional pyannote
3. **Clip Discovery Agent** — candidates, features, ranking
4. **Editing Agent** — edit plans (crop, captions, smart cut)
5. **Render Agent** — FFmpeg output + validation

## Shared services (not agents)

GPU Resource Manager, Model Manager, FFmpeg, Storage, Job, Progress, Caption, Face Tracking, Scene Detection, Audio Analysis, Ranking.

## Hardware

8 GB VRAM / 16 GB RAM. Serialize heavyweight GPU work via `GPUManager` (`MAX_CONCURRENT_GPU_JOBS=1`).

## Phase 1 scope

Foundation only: config, DB, Redis, Celery, health/system status, GPU/Model manager stubs. No video AI.
