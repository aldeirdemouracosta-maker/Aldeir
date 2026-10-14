"""ResourceMonitor: leitura de CPU, RAM e GPUs. Somente leitura."""
from __future__ import annotations

import subprocess
from typing import Callable

import psutil

_GPU_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
              "--format=csv,noheader,nounits"]


def _run_nvidia() -> str:
    return subprocess.run(_GPU_QUERY, capture_output=True, text=True, timeout=3, check=True).stdout


def parse_gpus(text: str) -> list[dict]:
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            gpus.append({"name": parts[0], "vram_total_mb": int(parts[1]), "vram_used_mb": int(parts[2])})
    return gpus


class ResourceMonitor:
    def __init__(self, gpu_query: Callable[[], str] = _run_nvidia) -> None:
        self._gpu_query = gpu_query
        psutil.cpu_percent(interval=None)  # primeira leitura é descartável

    def gpus(self) -> list[dict]:
        try:
            return parse_gpus(self._gpu_query())
        except (OSError, subprocess.SubprocessError):
            return []  # sem GPU NVIDIA/driver: lista vazia, não é erro

    def snapshot(self) -> dict:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_count": psutil.cpu_count(),
            "ram_total_mb": vm.total // 2**20,
            "ram_used_mb": (vm.total - vm.available) // 2**20,
            "ram_available_mb": vm.available // 2**20,
            "gpus": self.gpus(),
        }
