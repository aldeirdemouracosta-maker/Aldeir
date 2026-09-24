"""Registro de agentes de vídeo e roteamento para dispositivos.

Um agente é um papel com uma ferramenta local. Estar no registro não
significa estar disponível: ``route`` confere ferramenta, pesos, driver e
VRAM, e diz o motivo quando algo falta.
"""

from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .devices import Device
from .workspace import SYSTEM_MODELS  # modelos pequenos embutidos no ISO (RIFE, Real-ESRGAN)


@dataclass(frozen=True)
class Agent:
    id: str
    nome: str
    papel: str
    ferramentas: Sequence[str]      # executáveis aceitos (o primeiro encontrado vale)
    requer: str                     # "cpu" | "vulkan" | "cuda"
    vram_min_mib: int = 0
    pesos: Optional[str] = None     # glob relativo à pasta Modelos
    estado: str = "estavel"         # estavel | experimental | futuro
    pode_cpu: bool = False          # para "vulkan": aceita CPU como alternativa lenta


AGENTS: List[Agent] = [
    Agent("coordenador", "Coordenador", "entende o pedido e propõe tarefas (Qwen3 local)",
          ["llama-server"], "vulkan", 1500, "llm/*.gguf", pode_cpu=True),
    Agent("cortador", "Cortador", "corta trechos por tempo", ["ffmpeg"], "cpu"),
    Agent("silencios", "Removedor de silêncios", "retira pausas longas", ["auto-editor"], "cpu"),
    Agent("audio", "Áudio", "reduz ruído e normaliza volume", ["ffmpeg"], "cpu"),
    Agent("cenas", "Cenas", "detecta mudanças de cena (relatório CSV)", ["ffmpeg"], "cpu"),
    Agent("transcritor", "Transcritor", "gera legendas SRT com whisper.cpp",
          ["whisper-cli", "whisper-cpp"], "vulkan", 500, "whisper/ggml-*.bin", pode_cpu=True),
    Agent("legendas", "Legendas", "embute a legenda no vídeo", ["ffmpeg"], "cpu"),
    Agent("interpolador", "Interpolador", "câmera lenta / mais quadros (RIFE)",
          ["rife-ncnn-vulkan"], "vulkan", 1000, "rife/rife-v4.6/flownet.param"),
    Agent("upscaler", "Upscaler IA", "aumenta resolução (Real-ESRGAN)",
          ["realesrgan-ncnn-vulkan"], "vulkan", 1000, "realesrgan/models/*.param"),
    Agent("escala", "Escala", "muda resolução sem IA (lanczos)", ["ffmpeg"], "cpu"),
    Agent("exportador", "Exportador", "codifica o vídeo final (H.264)", ["ffmpeg"], "cpu"),
    Agent("gerador", "Gerador de vídeo", "cria vídeo a partir de texto (Wan2.1 / LTX-Video)",
          ["mini-ia-videos"], "cuda", 12000, None, "futuro"),
    Agent("editor_generativo", "Editor generativo", "troca fundo, remove objetos (VACE/DFVEdit/EditCtrl)",
          ["mini-ia-videos"], "cuda", 12000, None, "futuro"),
]

BY_ID: Dict[str, Agent] = {a.id: a for a in AGENTS}


@dataclass
class Assignment:
    agent: Agent
    device: Optional[Device]
    ferramenta: Optional[str]
    disponivel: bool
    motivos: List[str] = field(default_factory=list)


def _which(names: Sequence[str], extra_paths: Sequence[str] = ()) -> Optional[str]:
    for n in names:
        found = shutil.which(n)
        if found:
            return found
        for p in extra_paths:
            cand = os.path.join(p, n)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None




def find_weights(agent: Agent, models_dirs: Sequence[str]) -> List[str]:
    if not agent.pesos:
        return []
    hits: List[str] = []
    for base in models_dirs:
        hits += glob.glob(os.path.join(base, agent.pesos))
    return sorted(hits)


def _candidates(agent: Agent, devices: List[Device]) -> List[Device]:
    usable = [d for d in devices if d.usable]
    if agent.requer == "cpu":
        return [d for d in usable if d.kind == "cpu"]
    if agent.requer == "cuda":
        return [d for d in usable if d.kind == "cuda"]
    # vulkan: dGPU AMD primeiro, depois APU, depois NVIDIA (que também tem Vulkan)
    order = {"vulkan-dgpu": 0, "vulkan-apu": 1, "cuda": 2, "vulkan-sw": 3}
    gpus = sorted((d for d in usable if d.kind in order), key=lambda d: order[d.kind])
    if agent.pode_cpu:
        gpus += [d for d in usable if d.kind == "cpu"]
    return gpus


def route(agent: Agent, devices: List[Device], models_dirs: Sequence[str] = (SYSTEM_MODELS,),
          extra_paths: Sequence[str] = ()) -> Assignment:
    motivos: List[str] = []
    tool = _which(agent.ferramentas, extra_paths)
    if tool is None:
        motivos.append(f"ferramenta ausente: {' ou '.join(agent.ferramentas)}")
    weights = find_weights(agent, models_dirs)
    if agent.pesos and not weights:
        motivos.append(f"pesos ausentes em Modelos/{agent.pesos}")

    chosen = None
    for dev in _candidates(agent, devices):
        if dev.kind != "cpu" and agent.vram_min_mib and dev.vram_mib is not None:
            # APU usa RAM compartilhada: VRAM dedicada pequena não é limite real.
            if dev.kind != "vulkan-apu" and dev.vram_mib < agent.vram_min_mib:
                motivos.append(f"{dev.id}: {dev.vram_mib} MiB < {agent.vram_min_mib} MiB exigidos")
                continue
        chosen = dev
        break
    if chosen is None:
        need = {"cuda": "GPU NVIDIA com CUDA", "vulkan": "GPU com Vulkan (RADV)", "cpu": "CPU"}[agent.requer]
        motivos.append(f"nenhum dispositivo compatível: requer {need}"
                       + (f" com ≥{agent.vram_min_mib} MiB" if agent.vram_min_mib and agent.requer == "cuda" else ""))
    elif chosen.kind == "cpu" and agent.requer == "vulkan":
        motivos.append("sem GPU Vulkan: rodará na CPU (lento)")
    elif chosen.kind == "vulkan-sw":
        motivos.append("Vulkan por software: muito lento, só para teste")

    disponivel = tool is not None and chosen is not None and not (agent.pesos and not weights)
    if agent.estado == "futuro" and disponivel:
        motivos.append("recurso futuro: exige validação física em GPU CUDA")
    return Assignment(agent, chosen, tool, disponivel, motivos)


def route_all(devices: List[Device], models_dirs: Sequence[str] = (SYSTEM_MODELS,),
              extra_paths: Sequence[str] = ()) -> List[Assignment]:
    return [route(a, devices, models_dirs, extra_paths) for a in AGENTS]
