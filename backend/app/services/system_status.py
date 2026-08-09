from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import psutil

from app.core.config import get_settings
from app.schemas import GpuStatus, ModelStatus, SystemStatusResponse
from app.services.model_manager import get_model_manager


def _ffmpeg_info() -> dict[str, Any]:
    settings = get_settings()
    path = shutil.which(settings.ffmpeg_path) or settings.ffmpeg_path
    probe = shutil.which(settings.ffprobe_path) or settings.ffprobe_path
    info: dict[str, Any] = {
        "ffmpeg_installed": shutil.which(settings.ffmpeg_path) is not None,
        "ffprobe_installed": shutil.which(settings.ffprobe_path) is not None,
        "ffmpeg_path": path,
        "ffprobe_path": probe,
        "version": None,
    }
    if info["ffmpeg_installed"]:
        try:
            out = subprocess.run(
                [settings.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            first = (out.stdout or "").splitlines()
            info["version"] = first[0] if first else None
        except (OSError, subprocess.TimeoutExpired) as exc:
            info["error"] = str(exc)
    return info


def _gpu_status() -> tuple[GpuStatus, dict[str, Any]]:
    settings = get_settings()
    cuda_info: dict[str, Any] = {"installed": False, "version": None}
    gpu = GpuStatus(available=False, cuda_available=False)

    try:
        import torch  # type: ignore

        cuda_info["torch_version"] = torch.__version__
        cuda_info["installed"] = True
        cuda_info["version"] = getattr(torch.version, "cuda", None)
        if torch.cuda.is_available() and settings.gpu_enabled:
            gpu.available = True
            gpu.cuda_available = True
            gpu.device_count = torch.cuda.device_count()
            devices = []
            total = 0.0
            used = 0.0
            for i in range(gpu.device_count):
                props = torch.cuda.get_device_properties(i)
                free, tot = torch.cuda.mem_get_info(i)
                tot_mb = tot / (1024 * 1024)
                used_mb = (tot - free) / (1024 * 1024)
                total += tot_mb
                used += used_mb
                devices.append(
                    {
                        "index": i,
                        "name": props.name,
                        "vram_total_mb": round(tot_mb, 1),
                        "vram_used_mb": round(used_mb, 1),
                    }
                )
            gpu.devices = devices
            gpu.vram_total_mb = round(total, 1)
            gpu.vram_used_mb = round(used, 1)
    except ImportError:
        cuda_info["note"] = "torch not installed (optional in Phase 1)"

    if not gpu.available and shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if out.returncode != 0:
                gpu.available = False
                return gpu, cuda_info
            gpu.available = True
            devices = []
            for line in (out.stdout or "").strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    devices.append(
                        {
                            "name": parts[0],
                            "vram_total_mb": float(parts[1]),
                            "vram_used_mb": float(parts[2]),
                        }
                    )
            gpu.devices = devices
            if devices:
                gpu.vram_total_mb = sum(d["vram_total_mb"] for d in devices)
                gpu.vram_used_mb = sum(d["vram_used_mb"] for d in devices)
                gpu.device_count = len(devices)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            gpu.available = False

    return gpu, cuda_info


def _whisper_cache_present() -> bool:
    home = Path.home()
    candidates = [
        home / ".cache" / "huggingface" / "hub",
        home / ".cache" / "whisper",
    ]
    for path in candidates:
        if path.exists() and any(path.iterdir()):
            return True
    return False


def _ollama_status() -> dict[str, Any]:
    settings = get_settings()
    try:
        with httpx.Client(timeout=0.5) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            if response.status_code != 200:
                return {"reachable": False, "detail": f"HTTP {response.status_code}"}
            names = [m.get("name") for m in response.json().get("models", [])]
            return {
                "reachable": True,
                "models": names,
                "llm_present": any(settings.llm_model in (n or "") for n in names),
            }
    except httpx.HTTPError as exc:
        return {"reachable": False, "detail": str(exc)}


def _model_statuses(ollama: dict[str, Any] | None = None) -> list[ModelStatus]:
    settings = get_settings()
    ollama_info = ollama if ollama is not None else _ollama_status()
    model_manager = get_model_manager()
    return [
        ModelStatus(
            name="whisper",
            installed=_whisper_cache_present(),
            detail="faster-whisper cache detection (Phase 3 loads model)",
        ),
        ModelStatus(
            name="qwen",
            installed=bool(ollama_info.get("llm_present")),
            detail=f"Ollama model '{settings.llm_model}'",
        ),
        ModelStatus(
            name="qwen-vl",
            installed=False,
            detail="Optional; not required for MVP",
        ),
        ModelStatus(
            name="pyannote",
            installed=False,
            detail="Requires HF_TOKEN + Community-1 agreement (Phase 3)",
        ),
        ModelStatus(
            name="loaded_in_process",
            installed=bool(model_manager.loaded_names()),
            detail=",".join(model_manager.loaded_names()) or "none",
        ),
    ]


def _worker_status() -> dict[str, Any]:
    try:
        from app.workers.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=0.5)
        ping = inspector.ping() if inspector else None
        if not ping:
            return {"reachable": False, "detail": "no workers responded to ping"}
        return {"reachable": True, "workers": list(ping.keys())}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "detail": str(exc)}


def collect_system_status() -> SystemStatusResponse:
    settings = get_settings()
    vm = psutil.virtual_memory()
    disk_path = settings.storage_root if settings.storage_root.exists() else Path.cwd()
    disk = psutil.disk_usage(str(disk_path))
    gpu, cuda_info = _gpu_status()
    ollama = _ollama_status()

    return SystemStatusResponse(
        project=settings.project_name,
        gpu=gpu,
        cpu_percent=psutil.cpu_percent(interval=None),
        ram_used_mb=round(vm.used / (1024 * 1024), 1),
        ram_total_mb=round(vm.total / (1024 * 1024), 1),
        disk_used_gb=round(disk.used / (1024**3), 2),
        disk_total_gb=round(disk.total / (1024**3), 2),
        ffmpeg=_ffmpeg_info(),
        cuda=cuda_info,
        models=_model_statuses(ollama),
        workers=_worker_status(),
        ollama=ollama,
    )
