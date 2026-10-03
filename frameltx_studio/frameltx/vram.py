"""Detecção de GPU/VRAM e escolha automática do perfil de qualidade.

A detecção tenta, nesta ordem:
1. ``/system_stats`` do ComfyUI (a GPU que realmente vai gerar o vídeo);
2. ``nvidia-smi`` (funciona mesmo sem PyTorch no ambiente da interface);
3. ``torch.cuda`` se estiver instalado.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, replace

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GpuInfo:
    name: str
    vram_total_gb: float
    vram_free_gb: float | None = None
    source: str = "desconhecido"

    @property
    def summary(self) -> str:
        free = f", {self.vram_free_gb:.1f} GB livres" if self.vram_free_gb is not None else ""
        return f"{self.name} — {self.vram_total_gb:.1f} GB VRAM{free} (via {self.source})"


@dataclass(frozen=True)
class QualityProfile:
    """Parâmetros de geração ajustados para uma faixa de VRAM.

    Todas as resoluções são 9:16. FramePack exige múltiplos de 16 e o LTX
    múltiplos de 32 — por isso os números "quebrados".
    """

    key: str
    label: str
    min_vram_gb: float
    fp_width: int
    fp_height: int
    fp_steps: int
    # GB de VRAM que o FramePack mantém livres (maior = mais lento e mais seguro).
    fp_memory_preservation: float
    ltx_width: int
    ltx_height: int
    ltx_steps: int
    # Duração máxima de um único clipe LTX (clipes maiores são encadeados).
    ltx_max_seconds: int
    ltx_fps: int = 24
    fp_fps: int = 30

    @property
    def description(self) -> str:
        return (
            f"{self.label}: FramePack {self.fp_width}x{self.fp_height}, "
            f"LTX {self.ltx_width}x{self.ltx_height} (clipes de até {self.ltx_max_seconds}s)"
        )


# Ordenados do mais leve ao mais pesado.
PROFILES: tuple[QualityProfile, ...] = (
    QualityProfile("baixo", "Baixo (6–7 GB)", 0, 384, 672, 20, 3.5, 384, 672, 8, 4),
    QualityProfile("medio", "Médio (8–11 GB)", 7.5, 480, 832, 25, 6.0, 448, 800, 8, 5),
    QualityProfile("alto", "Alto (12–15 GB)", 11.5, 544, 960, 25, 6.0, 544, 960, 8, 8),
    QualityProfile("ultra", "Ultra (16 GB+)", 15.5, 640, 1136, 30, 8.0, 704, 1248, 8, 10),
)
PROFILE_BY_KEY = {p.key: p for p in PROFILES}


def _from_comfy(comfy_url: str) -> GpuInfo | None:
    try:
        resp = requests.get(f"{comfy_url}/system_stats", timeout=3)
        resp.raise_for_status()
        devices = [d for d in resp.json().get("devices", []) if d.get("type") == "cuda"]
    except (requests.RequestException, ValueError):
        return None
    if not devices:
        return None
    dev = max(devices, key=lambda d: d.get("vram_total", 0))
    gib = 1024**3
    return GpuInfo(
        name=str(dev.get("name", "GPU CUDA")).split(":")[-1].strip(),
        vram_total_gb=dev.get("vram_total", 0) / gib,
        vram_free_gb=dev.get("vram_free", 0) / gib,
        source="ComfyUI",
    )


def _from_nvidia_smi() -> GpuInfo | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            gpus.append(GpuInfo(parts[0], float(parts[1]) / 1024, float(parts[2]) / 1024, "nvidia-smi"))
    return max(gpus, key=lambda g: g.vram_total_gb) if gpus else None


def _from_torch() -> GpuInfo | None:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info(0)
    return GpuInfo(torch.cuda.get_device_name(0), total / 1024**3, free / 1024**3, "PyTorch")


def detect_gpu(comfy_url: str | None = None) -> GpuInfo | None:
    """Retorna a GPU NVIDIA com mais VRAM encontrada, ou ``None``."""
    probes = [lambda: _from_comfy(comfy_url)] if comfy_url else []
    probes += [_from_nvidia_smi, _from_torch]
    for probe in probes:
        info = probe()
        if info:
            log.info("GPU detectada: %s", info.summary)
            return info
    log.warning("Nenhuma GPU NVIDIA detectada")
    return None


def profile_for_vram(vram_gb: float | None) -> QualityProfile:
    """Escolhe o perfil mais pesado que cabe na VRAM disponível."""
    if vram_gb is None:
        return PROFILE_BY_KEY["medio"]
    chosen = PROFILES[0]
    for profile in PROFILES:
        if vram_gb >= profile.min_vram_gb:
            chosen = profile
    return chosen


def lower_profile(profile: QualityProfile) -> QualityProfile | None:
    """Perfil imediatamente mais leve — usado para tentar de novo após falta de VRAM."""
    idx = [p.key for p in PROFILES].index(profile.key) if profile.key in PROFILE_BY_KEY else 0
    if idx > 0:
        return PROFILES[idx - 1]
    # Já no mais leve: reduz ainda mais a resolução como último recurso.
    if profile.fp_width > 320:
        return replace(
            profile, key="minimo", label="Mínimo (emergência)",
            fp_width=320, fp_height=576, fp_memory_preservation=profile.fp_memory_preservation + 1,
            ltx_width=320, ltx_height=576, ltx_max_seconds=3,
        )
    return None


def resolve_profile(force_key: str, gpu: GpuInfo | None) -> QualityProfile:
    if force_key and force_key in PROFILE_BY_KEY:
        return PROFILE_BY_KEY[force_key]
    return profile_for_vram(gpu.vram_total_gb if gpu else None)
