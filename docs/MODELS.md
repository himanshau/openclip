# Models

OpenClip prefers local, open-weight models. **No paid inference APIs are required** for the core workflow.

## Categories

| Kind | Meaning |
|------|---------|
| Open-source code | Library/code license (MIT, Apache-2.0, etc.) |
| Open-weight model | Weights available for local use; license may differ from code |
| Account / token | May need Hugging Face login / accept terms (e.g. pyannote) |
| Paid API | Cloud inference billed per use — **optional adapters only** |

## Planned stack

| Component | Default | Notes |
|-----------|---------|--------|
| LLM | Qwen3-4B via Ollama | Quantized; unload when Whisper runs |
| Vision LLM | Qwen3-VL-4B | **Optional**; not in MVP path |
| ASR | faster-whisper `large-v3` | INT8 / INT8_FLOAT16 when supported |
| Alignment | WhisperX | Word timestamps |
| Diarization | pyannote Community-1 | May require `HF_TOKEN` + model agreement |
| CV | OpenCV, MediaPipe | Face / speaker framing |
| Scenes | PySceneDetect | CPU-friendly |
| Embeddings | Lightweight sentence-transformers | Only when needed |
| Ranking (future) | LightGBM | Interface only until trained |

## License diligence

Before adding a dependency, document:

1. Code license
2. Model weight license / terms
3. Whether an account/token is required
4. Whether any paid API is involved

Update this file when models are added.

## pyannote

`HF_TOKEN` may be required to download Community-1. Core transcription can run **without** diarization (speaker labels omitted).

## Paid APIs

OpenAI, Gemini, Claude, Groq, Deepgram, ElevenLabs, etc. must remain **optional**. The app must complete video → Shorts without them.
