# Agents

Five logical agents (implemented in later phases):

| Agent | Responsibility |
|-------|----------------|
| Media | Upload, validate, FFprobe, audio/proxy/thumbs |
| Transcript | ASR, alignment, diarization, word timestamps |
| Clip Discovery | Candidates, features, ranking, dedupe |
| Editing | Edit plans (crop, captions, smart cut) — not FFmpeg render |
| Render | FFmpeg → validated MP4 |

LLMs must not own file I/O, FFmpeg, DB writes, GPU scheduling, caption timestamps, face tracking, or encoding.
