# Troubleshooting

## Postgres / Redis

```bash
docker compose ps
docker compose logs postgres redis
```

Ensure `DATABASE_URL` / `REDIS_URL` match compose credentials.

## Celery worker not visible

Start worker with `--concurrency=1`. Check Redis broker URL.

## CUDA OOM (later phases)

Ensure only one GPU job; unload models between Whisper and Qwen.

## FFmpeg missing

Install FFmpeg and set `FFMPEG_PATH` / `FFPROBE_PATH`.
