# GPU setup

Target machine: **NVIDIA 8 GB VRAM**, **16 GB RAM**.

## Rules

1. Only one heavyweight model on GPU at a time (Whisper, Qwen, Qwen-VL, pyannote).
2. `MAX_CONCURRENT_GPU_JOBS=1` (default).
3. Unload previous model and clear CUDA cache before loading another.
4. Prefer quantized LLM + INT8 Whisper.
5. CPU fallback where practical.

## Docker GPU

With [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/):

- Build with `Dockerfile.gpu`
- Enable the `deploy.resources.reservations.devices` block under `ollama` (and worker) in `docker-compose.yml`

## Checks

```bash
python scripts/check_gpu.py
nvidia-smi
```

## Phase 1

GPU detection is reported by `/api/system/status`. No models are loaded yet.
