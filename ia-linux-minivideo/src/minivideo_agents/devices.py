"""Dispositivos de computação vistos pelos agentes.

Cada GPU é um dispositivo independente. Classes:
- ``cpu``: sempre existe.
- ``vulkan-dgpu``: GPU AMD dedicada com amdgpu (ex.: RX 580).
- ``vulkan-apu``: GPU integrada AMD (memória compartilhada com a RAM).
- ``cuda``: GPU NVIDIA com driver e nvidia-smi.
- ``vulkan-sw``: Vulkan por software (llvmpipe/lavapipe) — só para teste.
Nenhum modelo é dividido entre dispositivos diferentes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from minivideo_audit import audit

# IDs PCI de APUs AMD conhecidas (lista parcial; o resto cai na heurística).
AMD_APU_IDS = {
    "0x15dd": "Raven/Picasso", "0x15d8": "Picasso", "0x1636": "Renoir", "0x1638": "Cezanne",
    "0x164c": "Lucienne", "0x15e7": "Barcelo", "0x1681": "Rembrandt", "0x15bf": "Phoenix",
    "0x1506": "Mendocino", "0x163f": "Van Gogh",
}
APU_VRAM_HEURISTIC_MIB = 1024  # carve-out típico de APU; dGPUs amdgpu têm mais


@dataclass
class Device:
    id: str
    kind: str
    name: str
    vram_mib: Optional[int] = None
    driver: Optional[str] = None
    usable: bool = True
    notes: List[str] = field(default_factory=list)

    @property
    def vulkan(self) -> bool:
        return self.kind in ("vulkan-dgpu", "vulkan-apu", "vulkan-sw")


def classify(report: Dict) -> List[Device]:
    cpu = report["cpu"]
    flags = cpu["instrucoes"]
    cpu_dev = Device("cpu", "cpu", cpu.get("modelo") or "CPU")
    if flags.get("avx") and not flags.get("avx2"):
        cpu_dev.notes.append("sem AVX2: use binários compilados sem AVX2")
    devices = [cpu_dev]

    vk = report["vulkan"]
    vk_names = " ".join(d["nome"] for d in vk.get("dispositivos", []))
    vk_amd = any(k in vk_names for k in ("RADV", "AMD", "Radeon"))

    for g in report["gpus"]:
        if g["vendor"] != "0x1002":
            continue
        is_apu = g["device"] in AMD_APU_IDS or (g["vram_mib"] is not None and g["vram_mib"] <= APU_VRAM_HEURISTIC_MIB)
        dev = Device(f"amdgpu:{g['card']}", "vulkan-apu" if is_apu else "vulkan-dgpu",
                     g["nome"] or AMD_APU_IDS.get(g["device"], f"AMD {g['device']}"), g["vram_mib"], g["driver"])
        if is_apu and g["device"] not in AMD_APU_IDS:
            dev.notes.append("classificada como APU por heurística (VRAM dedicada pequena)")
        if is_apu:
            dev.notes.append("APU: memória compartilhada com a RAM do sistema (GTT)")
        if g["driver"] != "amdgpu":
            dev.usable = False
            dev.notes.append(f"driver '{g['driver']}' em vez de amdgpu: sem Vulkan RADV nem sensores")
        elif vk["estado"] != "presente" or not vk_amd:
            dev.usable = False
            dev.notes.append("Vulkan RADV não confirmado (vulkaninfo)")
        devices.append(dev)

    for g in report["cuda"].get("gpus", []):
        devices.append(Device(f"nvidia:{g['indice']}", "cuda", g["nome"], g["vram_mib"], "nvidia"))

    if "llvmpipe" in vk_names.lower() and not any(d.kind != "cpu" and d.usable for d in devices):
        devices.append(Device("vulkan:llvmpipe", "vulkan-sw", "Vulkan por software (llvmpipe)",
                              notes=["sem GPU: Vulkan emulado na CPU, muito lento — só para teste"]))
    return devices


def detect(root: str = "/") -> List[Device]:
    return classify(audit.collect(root))
