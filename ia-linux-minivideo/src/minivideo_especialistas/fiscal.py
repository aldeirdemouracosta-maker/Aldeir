"""Fiscal de hardware: aprova, reduz ou suspende a execução (JSON).

Usa só leitura: sensores do Safety Guard, /proc/meminfo e espaço em disco.
Nunca altera clocks, ventoinha ou firmware. Decisões são regras
determinísticas, não um modelo.
"""

from __future__ import annotations

import shutil
from typing import Dict, List, Optional

from minivideo_agents.executor import LIMITES_PADRAO
from minivideo_agents.registry import Assignment
from minivideo_guard.policy import PAUSAR, REDUZIR, GuardPolicy
from minivideo_guard.sensors import AmdgpuSysfsBackend, NvidiaSmiBackend

from . import schema

GPU_KINDS = ("vulkan-dgpu", "vulkan-apu", "vulkan-sw", "cuda")
QUADROS = ("interpolador", "upscaler")


def ram_disponivel_mib() -> Optional[float]:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


def leitura_gpu(sysfs_root: str = "/sys") -> Optional[Dict]:
    for backend in (AmdgpuSysfsBackend(sysfs_root), NvidiaSmiBackend()):
        devs = backend.discover()
        if devs:
            r = backend.read(devs[0])
            d = GuardPolicy().evaluate(r)
            return {"dispositivo": devs[0].id, "temp_edge_c": r.metrics["temp_edge_c"],
                    "vram_usada_mib": r.metrics["vram_used_mib"], "nivel": d.name, "nivel_num": d.level,
                    "motivos": d.reasons}
    return None


def estimar_disco_mib(tarefas: List[Dict], info: Optional[Dict]) -> float:
    """Estimativa conservadora: PNGs de quadros + intermediários mp4."""
    if not info or not info.get("video"):
        return 256.0
    w = int(info["video"].get("width") or 1280)
    h = int(info["video"].get("height") or 720)
    fps = info.get("fps") or 30.0
    total = 0.0
    tamanho = max(info.get("tamanho_mib") or 50.0, 1.0)
    for t in tarefas:
        p = t["params"]
        dur = (p["fim"] - p["inicio"]) if t["agente"] == "cortador" else info.get("duracao") or 60.0
        quadros = dur * fps
        png = w * h * 3 * 0.6 / 1048576  # MiB por quadro PNG (compressão ~40%)
        if t["agente"] == "interpolador":
            total += quadros * png * (1 + p.get("fator", 2))
        elif t["agente"] == "upscaler":
            total += quadros * png * (1 + 4)
        total += tamanho * 1.5
    return round(total, 1)


def fiscalizar(tarefas: List[Dict], assignments: Dict[str, Assignment], info: Optional[Dict], workdir: str,
               limites: Optional[Dict] = None, gpu: Optional[Dict] = "auto") -> Dict:
    """``tarefas``: lista de {cena, agente, params}. ``gpu``: leitura pronta, None, ou "auto"."""
    lim = dict(LIMITES_PADRAO, **(limites or {}))
    if gpu == "auto":
        gpu = leitura_gpu()
    ram = ram_disponivel_mib()
    try:
        livre = shutil.disk_usage(workdir).free / 1048576
    except OSError:
        livre = None
    estimativa = estimar_disco_mib(tarefas, info)
    motivos: List[str] = []
    geral = "aprovar"

    if livre is not None and livre - estimativa < lim["disco_reserva_mib"]:
        geral = "suspender"
        motivos.append(f"disco insuficiente: estimativa {estimativa:.0f} MiB + reserva "
                       f"{lim['disco_reserva_mib']:.0f} MiB > livre {livre:.0f} MiB")
    if ram is not None and ram < 1024:
        geral = "suspender"
        motivos.append(f"RAM disponível baixa: {ram:.0f} MiB (< 1024 MiB)")
    if ram is not None and ram < lim["memoria_max_mib"]:
        motivos.append(f"limite de memória por etapa ({lim['memoria_max_mib']:.0f} MiB) acima da RAM "
                       f"disponível ({ram:.0f} MiB): o sistema pode ficar sem memória antes do limite")

    saida: List[Dict] = []
    for i, t in enumerate(tarefas):
        a = assignments.get(t["agente"])
        dev = a.device if a else None
        dec, mot, aj = "aprovar", [], {}
        if a is None or not a.disponivel:
            dec = "suspender"
            mot.append("; ".join(a.motivos) if a else "agente desconhecido")
        elif dev is not None and dev.kind in GPU_KINDS:
            if gpu and dev.id == gpu["dispositivo"] and gpu["nivel_num"] >= PAUSAR:
                dec = "suspender"
                mot.append(f"GPU em nível '{gpu['nivel']}': aguarde esfriar ({'; '.join(gpu['motivos'])})")
            elif gpu and dev.id == gpu["dispositivo"] and gpu["nivel_num"] >= REDUZIR:
                dec = "reduzir"
                mot.append(f"GPU em nível '{gpu['nivel']}': carga reduzida")
                if t["agente"] == "upscaler":
                    aj["altura"] = min(int(t["params"].get("altura", 1080)), 720)
                if t["agente"] == "interpolador":
                    aj["fator"] = 2
            if dev.kind == "vulkan-sw" and t["agente"] == "upscaler":
                alvo = int(t["params"].get("altura", 1080))
                if alvo > lim["altura_max_gpu_vulkan_sw"]:
                    dec = "reduzir" if dec == "aprovar" else dec
                    aj["altura"] = min(aj.get("altura", alvo), int(lim["altura_max_gpu_vulkan_sw"]))
                    mot.append("Vulkan por software: altura limitada para caber no tempo")
            if gpu is None and dev.kind in ("vulkan-dgpu", "vulkan-apu", "cuda"):
                mot.append("sem leitura de sensores da GPU: o Safety Guard não poderá proteger esta etapa")
        saida.append({"indice": i, "cena": t["cena"], "agente": t["agente"],
                      "dispositivo": dev.id if dev else None, "decisao": dec, "motivos": mot, "ajustes": aj})

    if any(t["decisao"] == "suspender" for t in saida):
        geral = "suspender"
    elif geral == "aprovar" and any(t["decisao"] == "reduzir" for t in saida):
        geral = "reduzir"
    gpu_json = None if gpu is None else {k: v for k, v in gpu.items() if k != "nivel_num"}
    out = {"papel": "fiscal", "versao": 1, "decisao": geral, "motivos": motivos, "tarefas": saida,
           "recursos": {"ram_disponivel_mib": None if ram is None else round(ram, 1),
                        "disco_livre_mib": None if livre is None else round(livre, 1),
                        "estimativa_disco_mib": estimativa, "gpu": gpu_json},
           "limites": {k: lim[k] for k in ("tempo_max_etapa_s", "tempo_max_job_s", "memoria_max_mib",
                                           "disco_reserva_mib", "altura_max_gpu_vulkan_sw")}}
    return schema.check("fiscal", out)


def aplicar_ajustes(tarefas: List[Dict], fiscal: Dict) -> List[Dict]:
    """Aplica 'reduzir' do Fiscal aos parâmetros (cópia). Nunca aumenta carga."""
    novas = []
    for t, d in zip(tarefas, fiscal["tarefas"]):
        p = dict(t["params"])
        if d["decisao"] == "reduzir":
            if "altura" in d["ajustes"] and "altura" in p:
                p["altura"] = min(p["altura"], d["ajustes"]["altura"])
            if "fator" in d["ajustes"] and "fator" in p:
                p["fator"] = min(p["fator"], d["ajustes"]["fator"])
        novas.append({**t, "params": p})
    return novas
