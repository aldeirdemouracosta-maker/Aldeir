"""Diagnóstico da máquina local: rode antes da Fase 3 real.

    python scripts/check_hardware.py
Lê as mesmas variáveis CINEFORJA_* dos workers e relata o que está pronto.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cineforja import config  # noqa: E402


def run(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r)
    except Exception:
        return None


def line(ok: bool | None, name: str, detail: str = "") -> None:
    print(f"[{'OK' if ok else '--' if ok is None else 'FALHA'}] {name}" + (f": {detail}" if detail else ""))


def main() -> None:
    cfg = config.load()
    gpus = run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"])
    line(bool(gpus), "NVIDIA (CUDA)", gpus or "nvidia-smi indisponível")
    vk = run(["vulkaninfo", "--summary"]) if shutil.which("vulkaninfo") else None
    line(bool(vk), "Vulkan", "vulkaninfo ok (confira se a RX 570 aparece)" if vk else "vulkaninfo indisponível")
    line(bool(shutil.which("ffmpeg")), "ffmpeg")

    if cfg.ollama_url:
        tags = get(f"{cfg.ollama_url}/api/tags")
        names = [m["name"] for m in (tags or {}).get("models", [])]
        line(tags is not None, "Ollama", ", ".join(names) or "sem modelos")
        for label, m in (("LLM", cfg.llm_model), ("VLM", cfg.vlm_model)):
            if m:
                line(any(n == m or n.startswith(m + ":") for n in names), f"modelo {label} '{m}'")
    else:
        line(None, "Ollama", "CINEFORJA_OLLAMA_URL não definida (LLM ficará simulado)")

    if cfg.comfy_url:
        st = get(f"{cfg.comfy_url}/system_stats")
        line(st is not None, "ComfyUI", cfg.comfy_url)
        for label, p in (("vídeo", cfg.comfy_workflow_video), ("imagem", cfg.comfy_workflow_image)):
            if p:
                line(os.path.isfile(p), f"workflow {label}", p)
    else:
        line(None, "ComfyUI", "CINEFORJA_COMFY_URL não definida (vídeo ficará simulado)")

    if cfg.sd_bin:
        line(os.path.isfile(cfg.sd_bin) and os.access(cfg.sd_bin, os.X_OK), "stable-diffusion.cpp", cfg.sd_bin)
        line(bool(cfg.sd_model and os.path.isfile(cfg.sd_model)), "modelo sd.cpp", cfg.sd_model or "não definido")
    else:
        line(None, "stable-diffusion.cpp", "CINEFORJA_SD_BIN não definida (imagem leve ficará simulada)")


if __name__ == "__main__":
    main()
