"""``minivideo-audit`` — diagnóstico reproduzível e somente leitura.

Não usa root, não acessa a rede, não baixa modelos e não altera o sistema.
Só lê /proc e /sys, procura executáveis no PATH, consulta versões com
timeout e lista (sem abrir) arquivos de pesos em pastas informadas.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

TOOLS = {
    # nome lógico: (executáveis candidatos, argumentos de versão ou None)
    "ffmpeg": (["ffmpeg"], ["-version"]),
    "ffprobe": (["ffprobe"], ["-version"]),
    "pyscenedetect": (["scenedetect"], ["version"]),
    "auto-editor": (["auto-editor"], ["--version"]),
    "whisper.cpp": (["whisper-cli", "whisper-cpp", "whisper"], None),
    "rife-ncnn-vulkan": (["rife-ncnn-vulkan"], None),
    "realesrgan-ncnn-vulkan": (["realesrgan-ncnn-vulkan"], None),
    "vulkaninfo": (["vulkaninfo"], None),
    "nvidia-smi": (["nvidia-smi"], None),
    "llama-server (orquestrador)": (["llama-server"], None),
    "mini-ia-videos": (["mini-ia-videos"], ["--help"]),
}

PY_MODULES = ["scenedetect", "auto_editor", "numpy", "cv2", "PIL", "torch", "diffusers",
              "transformers", "lpips", "open_clip", "skimage"]

WEIGHT_PATTERNS = [
    ("whisper.cpp (ggml)", re.compile(r"^ggml-.*\.bin$")),
    ("ncnn (RIFE/Real-ESRGAN)", re.compile(r".*\.param$")),
    ("safetensors (Wan/LTX/DFVEdit/EditCtrl)", re.compile(r".*\.safetensors$")),
    ("gguf (Qwen orquestrador)", re.compile(r".*\.gguf$")),
]

GENERATIVE = ["wan-vace-1.3b", "ltx-video-2b-distilled", "dfvedit-wan-1.3b", "editctrl-1.3b"]


def _run(cmd: List[str], timeout: float = 8.0) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (out.stdout or "") + (out.stderr or "")


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def cpu_info(root: str) -> Dict:
    text = _read(os.path.join(root, "proc/cpuinfo")) or ""
    model = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
    flags_line = re.search(r"^flags\s*:\s*(.+)$", text, re.M)
    flags = set(flags_line.group(1).split()) if flags_line else set()
    return {
        "modelo": model.group(1).strip() if model else None,
        "threads_logicos": len(re.findall(r"^processor\s*:", text, re.M)) or None,
        "instrucoes": {f: f in flags for f in ("sse4_2", "avx", "f16c", "fma", "avx2", "avx512f")},
    }


def memory_info(root: str) -> Dict:
    text = _read(os.path.join(root, "proc/meminfo")) or ""
    def kib(key):
        m = re.search(rf"^{key}:\s*(\d+)", text, re.M)
        return int(m.group(1)) if m else None
    total, avail = kib("MemTotal"), kib("MemAvailable")
    return {"total_gib": round(total / 1048576, 1) if total else None,
            "disponivel_gib": round(avail / 1048576, 1) if avail else None}


def disk_info(paths: List[str]) -> List[Dict]:
    out = []
    for p in paths:
        try:
            u = shutil.disk_usage(p)
        except OSError:
            continue
        out.append({"caminho": p, "livre_gib": round(u.free / 2**30, 1), "total_gib": round(u.total / 2**30, 1)})
    return out


PCI_NAMES = {("0x1002", "0x67df"): "AMD Polaris 10/20 (RX 470/480/570/580)",
             ("0x1002", "0x6fdf"): "AMD Polaris 20 XL (RX 580 2048SP)"}


def gpu_info(root: str) -> List[Dict]:
    drm = os.path.join(root, "sys/class/drm")
    gpus = []
    try:
        entries = sorted(e for e in os.listdir(drm) if re.fullmatch(r"card\d+", e))
    except OSError:
        return gpus
    for e in entries:
        dev = os.path.join(drm, e, "device")
        vendor = (_read(os.path.join(dev, "vendor")) or "").strip()
        device = (_read(os.path.join(dev, "device")) or "").strip()
        drv_link = os.path.join(dev, "driver")
        driver = os.path.basename(os.path.realpath(drv_link)) if os.path.exists(drv_link) else None
        vram = (_read(os.path.join(dev, "mem_info_vram_total")) or "").strip()
        gpus.append({
            "card": e, "vendor": vendor, "device": device, "driver": driver,
            "nome": PCI_NAMES.get((vendor, device)),
            "vram_mib": round(int(vram) / 1048576) if vram.isdigit() else None,
        })
    return gpus


def vulkan_info() -> Dict:
    if not shutil.which("vulkaninfo"):
        return {"estado": "indisponivel", "motivo": "vulkaninfo ausente (pacote vulkan-tools)", "dispositivos": []}
    out = _run(["vulkaninfo", "--summary"], timeout=15)
    if out is None:
        return {"estado": "erro", "motivo": "vulkaninfo não respondeu", "dispositivos": []}
    names = re.findall(r"deviceName\s*=\s*(.+)", out)
    drivers = re.findall(r"driverName\s*=\s*(.+)", out)
    devs = [{"nome": n.strip(), "driver": (drivers[i].strip() if i < len(drivers) else None)} for i, n in enumerate(names)]
    real = [d for d in devs if "llvmpipe" not in d["nome"].lower()]
    estado = "presente" if real else ("somente_software" if devs else "sem_dispositivo")
    return {"estado": estado, "dispositivos": devs}


def cuda_info() -> Dict:
    if not shutil.which("nvidia-smi"):
        return {"estado": "indisponivel", "motivo": "nvidia-smi ausente (sem driver NVIDIA)", "gpus": []}
    out = _run(["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits"])
    gpus = []
    for line in (out or "").strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4 and parts[2].isdigit():
            gpus.append({"indice": parts[0], "nome": parts[1], "vram_mib": int(parts[2]), "driver": parts[3]})
    return {"estado": "presente" if gpus else "erro", "gpus": gpus}


def tools_info() -> Dict[str, Dict]:
    result = {}
    for name, (candidates, version_args) in TOOLS.items():
        path = next((shutil.which(c) for c in candidates if shutil.which(c)), None)
        entry = {"estado": "presente" if path else "ausente", "caminho": path}
        if path and version_args:
            out = _run([path] + version_args)
            entry["versao"] = (out or "").strip().splitlines()[0][:160] if out and out.strip() else None
            if name == "mini-ia-videos" and out:
                entry["subcomandos_help"] = out[:4000]
        result[name] = entry
    return result


def python_modules() -> Dict[str, bool]:
    found = {}
    for mod in PY_MODULES:
        try:
            found[mod] = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            found[mod] = False
    return found


def find_weights(dirs: List[str], max_depth: int = 4, limit: int = 200) -> List[Dict]:
    hits = []
    for base in dirs:
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            hits.append({"pasta": base, "erro": "pasta não existe"})
            continue
        base_depth = base.rstrip(os.sep).count(os.sep)
        for cur, subdirs, files in os.walk(base):
            if cur.count(os.sep) - base_depth >= max_depth:
                subdirs[:] = []
            for f in files:
                for kind, rx in WEIGHT_PATTERNS:
                    if rx.match(f):
                        full = os.path.join(cur, f)
                        try:
                            size = os.path.getsize(full)
                        except OSError:
                            size = None
                        hits.append({"tipo": kind, "arquivo": full,
                                     "tamanho_mib": round(size / 1048576, 1) if size else None})
                        if len(hits) >= limit:
                            return hits
    return hits


def orchestrator_env() -> Dict:
    keys = ["MINI_IA_VIDEOS_ORCHESTRATOR_URL", "MINI_IA_VIDEOS_ORCHESTRATOR_MODEL",
            "MINI_IA_VIDEOS_ORCHESTRATOR_TIMEOUT"]
    return {k: os.environ.get(k) for k in keys}


def choose_profile(report: Dict) -> Dict:
    cpu = report["cpu"]["instrucoes"]
    cuda_gpus = report["cuda"]["gpus"]
    vk = report["vulkan"]
    amd = [g for g in report["gpus"] if g["vendor"] == "0x1002"]
    tools = report["ferramentas"]
    max_vram = max((g["vram_mib"] for g in cuda_gpus), default=0)

    perfis, indisponivel, avisos = [], [], []
    if max_vram >= 15500:
        perfis.append("cuda16")
    elif max_vram >= 11500:
        perfis.append("cuda12 (faixa mínima, sujeita a testes)")
    elif cuda_gpus:
        avisos.append(f"GPU CUDA com {max_vram} MiB: abaixo de 12 GB, geração pesada não recomendada")
    if vk["estado"] == "presente":
        perfis.append("vulkan")
    elif amd:
        avisos.append("GPU AMD detectada, mas Vulkan não confirmado (instale vulkan-tools e rode vulkaninfo)")
    perfis.append("cpu")

    if not any(p.startswith("cuda") for p in perfis):
        indisponivel += [f"{e}: requer CUDA (NVIDIA ≥12 GB VRAM)" for e in GENERATIVE]
    if vk["estado"] != "presente":
        indisponivel += ["interpolação RIFE NCNN: requer Vulkan", "upscale Real-ESRGAN NCNN: requer Vulkan"]
    for tool, uso in [("ffmpeg", "toda edição/exportação"), ("whisper.cpp", "transcrição/legendas"),
                      ("pyscenedetect", "detecção de cenas"), ("auto-editor", "remoção de silêncios"),
                      ("rife-ncnn-vulkan", "interpolação/slow motion"), ("realesrgan-ncnn-vulkan", "upscale")]:
        if tools[tool]["estado"] != "presente":
            indisponivel.append(f"{uso}: '{tool}' ausente")
    if cpu.get("avx") and not cpu.get("avx2"):
        avisos.append("CPU sem AVX2: binários pré-compilados com AVX2 (whisper.cpp, llama.cpp, wheels) "
                      "podem falhar com SIGILL; compile com -DGGML_AVX2=OFF ou -march=native")
    if tools["mini-ia-videos"]["estado"] != "presente":
        avisos.append("comando 'mini-ia-videos' não encontrado no PATH")
    return {"perfis": perfis, "indisponivel": indisponivel, "avisos": avisos}


def collect(root: str = "/", models_dirs: Optional[List[str]] = None) -> Dict:
    report = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "sistema": {"kernel": platform.release(), "python": sys.version.split()[0], "maquina": platform.machine()},
        "cpu": cpu_info(root),
        "memoria": memory_info(root),
        "disco": disk_info([os.getcwd(), os.path.expanduser("~")]),
        "gpus": gpu_info(root),
        "vulkan": vulkan_info(),
        "cuda": cuda_info(),
        "ferramentas": tools_info(),
        "modulos_python": python_modules(),
        "pesos": find_weights(models_dirs or []),
        "orquestrador_env": orchestrator_env(),
    }
    report["perfil"] = choose_profile(report)
    return report


def render_text(r: Dict) -> str:
    L = []
    c = r["cpu"]
    flags = " ".join(f"{k}={'sim' if v else 'não'}" for k, v in c["instrucoes"].items())
    L.append(f"CPU: {c['modelo']} — {c['threads_logicos']} threads — {flags}")
    L.append(f"RAM: {r['memoria']['total_gib']} GiB (disponível {r['memoria']['disponivel_gib']} GiB)")
    for d in r["disco"]:
        L.append(f"Disco {d['caminho']}: {d['livre_gib']} GiB livres de {d['total_gib']} GiB")
    if not r["gpus"]:
        L.append("GPU (sysfs): nenhuma encontrada em /sys/class/drm")
    for g in r["gpus"]:
        L.append(f"GPU {g['card']}: {g['nome'] or ''} vendor={g['vendor']} device={g['device']} "
                 f"driver={g['driver']} VRAM={g['vram_mib'] or 'n/d'} MiB")
    L.append(f"Vulkan: {r['vulkan']['estado']} {r['vulkan'].get('motivo', '')} "
             + ", ".join(d["nome"] for d in r["vulkan"]["dispositivos"]))
    L.append(f"CUDA: {r['cuda']['estado']} {r['cuda'].get('motivo', '')} "
             + ", ".join(f"{g['nome']} {g['vram_mib']} MiB" for g in r["cuda"]["gpus"]))
    L.append("Ferramentas:")
    for name, t in r["ferramentas"].items():
        L.append(f"  {name:<28} {t['estado']:<8} {t.get('versao') or t.get('caminho') or ''}")
    L.append("Módulos Python: " + ", ".join(f"{m}={'sim' if v else 'não'}" for m, v in r["modulos_python"].items()))
    L.append(f"Pesos encontrados: {len([p for p in r['pesos'] if 'arquivo' in p])}")
    for p in r["pesos"]:
        L.append(f"  {p.get('tipo', '')} {p.get('arquivo', p.get('pasta'))} {p.get('tamanho_mib', p.get('erro', ''))}")
    orq = r["orquestrador_env"]
    L.append("Orquestrador: " + ("configurado " + str(orq) if any(orq.values()) else "não configurado (modo rules)"))
    L.append(f"Perfis possíveis: {', '.join(r['perfil']['perfis'])}")
    for a in r["perfil"]["avisos"]:
        L.append(f"  AVISO: {a}")
    L.append("Indisponível nesta máquina:")
    for i in r["perfil"]["indisponivel"]:
        L.append(f"  - {i}")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="minivideo-audit",
                                description="Auditoria somente leitura da máquina para o IA-Linux MiniVideo.")
    p.add_argument("--json", action="store_true", help="saída JSON")
    p.add_argument("--models-dir", action="append", default=[], help="pasta de pesos a listar (repetível)")
    p.add_argument("-o", "--output", help="grava o relatório JSON neste arquivo")
    p.add_argument("--root", default="/", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    env_models = os.environ.get("MINI_IA_VIDEOS_MODELS")
    report = collect(args.root, args.models_dir + ([env_models] if env_models else []))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0
