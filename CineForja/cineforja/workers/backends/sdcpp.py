"""stable-diffusion.cpp (binário `sd`, build Vulkan) como subprocesso: sem modelo residente."""
from __future__ import annotations

import os
import subprocess

from .ollama import BackendError


def generate(sd_bin: str, model: str, prompt: str, out_path: str, *, width: int = 512,
             height: int = 512, steps: int = 20, seed: int = 42, timeout: float = 900) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cmd = [sd_bin, "-m", model, "-p", prompt, "-o", out_path,
           "-W", str(width), "-H", str(height), "--steps", str(steps), "-s", str(seed)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackendError(f"sd.cpp: {exc}") from exc
    if r.returncode != 0 or not os.path.exists(out_path):
        raise BackendError(f"sd.cpp falhou (código {r.returncode}): {r.stderr[-300:]}")
    return out_path
