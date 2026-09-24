"""Catálogo de motores: quais exigem CUDA, Vulkan ou CPU.

O Editor só pode escolher motores deste catálogo, e só para os agentes
listados em ``agentes``. VRAM "alvo" = limite de projeto, não medição.
Licenças conferidas nos arquivos LICENSE dos repositórios em 2026-09-24.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Motor:
    id: str
    nome: str
    agentes: Tuple[str, ...]
    backends: Tuple[str, ...]           # subconjunto de ("cpu", "vulkan", "cuda")
    vram_min_mib: Optional[int]         # None = não se aplica / não medido
    estado: str                         # estavel | experimental | futuro
    no_iso: bool
    licenca: str
    fonte: str
    nota: str = ""


MOTORES: List[Motor] = [
    Motor("ffmpeg", "FFmpeg 6.1", ("cortador", "audio", "cenas", "escala", "legendas", "exportador", "montador"),
          ("cpu",), None, "estavel", True, "LGPL/GPL (build GPL com x264)", "https://ffmpeg.org",
          "exportação por VA-API na RX 580 (H.264/HEVC, sem B-frames)"),
    Motor("auto-editor", "Auto-Editor 31.6.0", ("silencios",), ("cpu",), None, "estavel", True, "Unlicense",
          "https://github.com/WyattBlue/auto-editor", "binário oficial; testado sem AVX2 (CPU emulada)"),
    Motor("whisper.cpp", "whisper.cpp 1.9.4", ("transcritor",), ("cpu", "vulkan", "cuda"), 500, "estavel", True,
          "MIT", "https://github.com/ggml-org/whisper.cpp", "no ISO: CPU + Vulkan; CUDA só em build próprio"),
    Motor("rife-ncnn-vulkan", "RIFE v4.6 (ncnn)", ("interpolador",), ("vulkan",), 1000, "estavel", True, "MIT",
          "https://github.com/nihui/rife-ncnn-vulkan", "release 20221029"),
    Motor("realesrgan-ncnn-vulkan", "Real-ESRGAN (ncnn)", ("upscaler",), ("vulkan",), 1000, "estavel", True,
          "BSD-3-Clause", "https://github.com/xinntao/Real-ESRGAN", "release v0.2.5.0"),
    Motor("llama.cpp", "llama.cpp + Qwen3 (GGUF)", ("diretor", "editor"), ("cpu", "vulkan", "cuda"), 1500,
          "estavel", True, "MIT", "https://github.com/ggml-org/llama.cpp",
          "opcional: sem modelo, Diretor e Editor usam regras"),
    Motor("stable-diffusion.cpp", "stable-diffusion.cpp", ("quadro_chave",), ("cpu", "vulkan", "cuda"), 4000,
          "experimental", False, "MIT", "https://github.com/leejet/stable-diffusion.cpp",
          "Wan em Vulkan é lento e tem regressões abertas; não integrado"),
    Motor("wan2.1-vace-1.3b", "Wan2.1 VACE 1.3B", ("gerador", "editor_generativo"), ("cuda",), 12000,
          "futuro", False, "Apache-2.0 (código VACE)", "https://github.com/ali-vilab/VACE",
          "vace_wan_inference.py --src_video --src_mask --src_ref_images --prompt; 480p"),
    Motor("editctrl-1.3b", "EditCtrl (Wan2.1 VACE 1.3B)", ("editor_generativo",), ("cuda",), 12000, "futuro", False,
          "Apache-2.0", "https://github.com/yehonathanlitman/EditCtrl",
          "reimplementação pública sobre DiffSynth-Studio; exige máscara de vídeo"),
    Motor("dfvedit-wan-1.3b", "DFVEdit (Wan2.1 1.3B)", ("editor_generativo",), ("cuda",), 12000, "futuro", False,
          "verificar no repositório", "", "sem repositório conferido nesta sessão"),
    Motor("ltx-2", "LTX-2 (ltx-pipelines)", ("gerador",), ("cuda",), 16000, "futuro", False,
          "LTX Community License (uso comercial ≥ US$10 mi/ano exige licença paga)",
          "https://github.com/Lightricks/LTX-2", "python -m ltx_pipelines.ti2vid_two_stages"),
    Motor("wan2.2-ti2v-5b", "Wan2.2 TI2V-5B", ("gerador",), ("cuda",), 24000, "futuro", False, "Apache-2.0",
          "https://github.com/Wan-Video/Wan2.2", "README: ≥24 GB (RTX 4090) com offload; acima do alvo de 16 GB"),
]

BY_ID: Dict[str, Motor] = {m.id: m for m in MOTORES}


def motores_para(agente: str) -> List[Motor]:
    return [m for m in MOTORES if agente in m.agentes]


def matriz_texto() -> str:
    head = f"{'motor':<24} {'CPU':^5} {'Vulkan':^7} {'CUDA':^5} {'VRAM mín.':>10}  {'estado':<12} {'no ISO':<6} licença"
    lines = [head, "-" * len(head)]
    for m in MOTORES:
        mark = lambda b: "sim" if b in m.backends else "-"  # noqa: E731
        vram = f"{m.vram_min_mib} MiB" if m.vram_min_mib else "-"
        lines.append(f"{m.id:<24} {mark('cpu'):^5} {mark('vulkan'):^7} {mark('cuda'):^5} {vram:>10}  "
                     f"{m.estado:<12} {'sim' if m.no_iso else 'não':<6} {m.licenca}")
    return "\n".join(lines)
