#!/usr/bin/env python3
"""Report GPU / CUDA availability. Does not download models."""

from __future__ import annotations

import json
import shutil
import subprocess


def main() -> int:
    report: dict = {
        "nvidia_smi": shutil.which("nvidia-smi") is not None,
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "torch_installed": False,
    }

    if report["nvidia_smi"]:
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            for line in (out.stdout or "").strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    report["devices"].append(
                        {
                            "index": parts[0],
                            "name": parts[1],
                            "memory_total_mb": parts[2],
                            "memory_used_mb": parts[3],
                        }
                    )
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["nvidia_smi_error"] = str(exc)

    try:
        import torch  # type: ignore

        report["torch_installed"] = True
        report["cuda_available"] = bool(torch.cuda.is_available())
        report["device_count"] = int(torch.cuda.device_count()) if report["cuda_available"] else 0
        report["torch_version"] = torch.__version__
        if report["cuda_available"]:
            report["cuda_version"] = getattr(torch.version, "cuda", None)
    except ImportError:
        report["torch_note"] = "torch not installed (optional until ML phases)"

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
