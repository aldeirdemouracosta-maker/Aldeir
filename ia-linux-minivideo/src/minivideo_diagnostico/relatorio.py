"""minivideo-diagnostico: relatório do hardware real num arquivo.

Somente leitura e sem root: não altera clocks, ventoinha nem firmware (mesma
regra do Safety Guard). Os testes funcionais usam arquivos temporários em
/tmp e cada um tem tempo limite. O resultado vai para
Logs/diagnostico-<data>.txt (legível) e .json (para análise), prontos para
copiar num pendrive e enviar.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional

from minivideo_agents.workspace import Workspace
from minivideo_audit import audit

OK, FALHOU, AUSENTE = "OK", "FALHOU", "AUSENTE"


def rodar(cmd: List[str], timeout: float = 30, env: Optional[Dict] = None) -> Dict:
    """Executa e devolve {cmd, codigo, saida, segundos}; nunca levanta exceção."""
    t0 = time.time()
    if not shutil.which(cmd[0]):
        return {"cmd": " ".join(cmd), "codigo": None, "saida": f"{cmd[0]} ausente", "segundos": 0.0}
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, env=env)
        saida, codigo = r.stdout.decode("utf-8", "replace"), r.returncode
    except subprocess.TimeoutExpired as exc:
        saida, codigo = (exc.stdout or b"").decode("utf-8", "replace") + f"\n(tempo limite de {timeout:.0f} s)", -999
    except OSError as exc:
        saida, codigo = str(exc), -998
    return {"cmd": " ".join(cmd), "codigo": codigo, "saida": saida[-6000:], "segundos": round(time.time() - t0, 2)}


def _ler(caminho: str) -> str:
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def sistema() -> Dict:
    flags = ""
    for linha in _ler("/proc/cpuinfo").splitlines():
        if linha.startswith("flags"):
            flags = linha.split(":", 1)[1].split()
            break
    return {
        "kernel": platform.release(),
        "boot": "UEFI" if os.path.isdir("/sys/firmware/efi") else "BIOS/legado",
        "cmdline": _ler("/proc/cmdline"),
        "release": _ler("/etc/minivideo-release"),
        "cpu_instrucoes": {f: f in flags for f in ("sse4_2", "avx", "f16c", "fma", "avx2", "avx512f")},
        "placa": {k: _ler(f"/sys/class/dmi/id/{k}") for k in ("board_vendor", "board_name", "bios_version",
                                                              "bios_date")},
    }


def placas_de_video() -> List[Dict]:
    out = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        dev = os.path.join(card, "device")
        drv = os.path.basename(os.path.realpath(os.path.join(dev, "driver"))) if os.path.exists(
            os.path.join(dev, "driver")) else None
        out.append({"card": os.path.basename(card), "vendor": _ler(os.path.join(dev, "vendor")),
                    "device": _ler(os.path.join(dev, "device")), "driver": drv,
                    "vram_total": _ler(os.path.join(dev, "mem_info_vram_total")) or None,
                    "vbios": _ler(os.path.join(dev, "vbios_version")) or None})
    return out


def coletas() -> Dict[str, Dict]:
    render = sorted(glob.glob("/dev/dri/renderD*"))
    c = {
        "lspci": rodar(["lspci", "-nnk"]),
        "vulkaninfo": rodar(["vulkaninfo", "--summary"]),
        "vainfo": rodar(["vainfo", "--display", "drm", "--device", render[0]] if render else ["vainfo"]),
        "aplay": rodar(["aplay", "-l"]),
        "rede": rodar(["ip", "-br", "addr"]),
        "discos": rodar(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT,MODEL"]),
        "memoria": rodar(["free", "-m"]),
    }
    # dmesg costuma exigir root; sem permissão fica registrado, não é falha do hardware
    c["dmesg_gpu"] = rodar(["dmesg"])
    if c["dmesg_gpu"]["codigo"] == 0:
        linhas = [l for l in c["dmesg_gpu"]["saida"].splitlines()
                  if any(k in l.lower() for k in ("amdgpu", "drm", "firmware", "error", "fail"))]
        c["dmesg_gpu"]["saida"] = "\n".join(linhas[-150:])
    return c


def sensores() -> List[Dict]:
    from minivideo_guard.sensors import AmdgpuSysfsBackend
    b = AmdgpuSysfsBackend()
    out = []
    for d in b.discover():
        r = b.read(d)
        out.append({"id": d.id, "metricas": r.metrics, "avisos": r.errors})
    return out


def testes_funcionais(completo: bool = False) -> List[Dict]:
    """Testes curtos que exercitam GPU e codificador de verdade."""
    res: List[Dict] = []
    tmp = tempfile.mkdtemp(prefix="minivideo-diag-")
    try:
        render = sorted(glob.glob("/dev/dri/renderD*"))
        clipe = os.path.join(tmp, "clipe.mp4")
        r = rodar(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24", "-t", "2",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", clipe], 60)
        res.append({"teste": "ffmpeg (CPU, libx264)", **r})
        if render:
            r = rodar(["ffmpeg", "-y", "-v", "error", "-vaapi_device", render[0], "-f", "lavfi", "-i",
                       "testsrc2=size=1280x720:rate=24", "-t", "2", "-vf", "format=nv12,hwupload",
                       "-c:v", "h264_vaapi", "-bf", "0", os.path.join(tmp, "vaapi.mp4")], 60)
            res.append({"teste": "VA-API h264 (RX 580 sem B-frames)", **r})
        else:
            res.append({"teste": "VA-API h264", "cmd": "", "codigo": None, "saida": "sem /dev/dri/renderD*",
                        "segundos": 0.0})
        quadros = os.path.join(tmp, "q")
        os.makedirs(quadros)
        rodar(["ffmpeg", "-v", "error", "-i", clipe, "-frames:v", "2", os.path.join(quadros, "%08d.png")], 30)
        rife = "/usr/share/minivideo/modelos/rife/rife-v4.6"
        if os.path.isdir(rife):
            os.makedirs(os.path.join(tmp, "qr"))
            r = rodar(["rife-ncnn-vulkan", "-i", quadros, "-o", os.path.join(tmp, "qr"), "-m", rife, "-n", "4"], 120)
            res.append({"teste": "RIFE (Vulkan)", **r})
        esr = "/usr/share/minivideo/modelos/realesrgan/models"
        if os.path.isdir(esr):
            r = rodar(["realesrgan-ncnn-vulkan", "-i", os.path.join(quadros, "00000001.png"), "-o",
                       os.path.join(tmp, "up.png"), "-m", esr, "-n", "realesr-animevideov3", "-s", "2"], 120)
            res.append({"teste": "Real-ESRGAN (Vulkan)", **r})
        if completo:
            ws = Workspace()
            ggufs = sorted(glob.glob(os.path.join(ws.path("Modelos"), "llm", "*.gguf")), key=os.path.getsize)
            if ggufs:
                r = rodar(["llama-bench", "-m", ggufs[0], "-p", "64", "-n", "32", "-ngl", "99", "-o", "json"], 600)
                res.append({"teste": f"llama-bench {os.path.basename(ggufs[0])} (Vulkan)", **r})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for t in res:
        t["resultado"] = AUSENTE if t["codigo"] is None else (OK if t["codigo"] == 0 else FALHOU)
    return res


def montar(completo: bool = False, funcionais: bool = True) -> Dict:
    return {
        "formato": "minivideo-diagnostico/1",
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sistema": sistema(),
        "placas_de_video": placas_de_video(),
        "sensores": sensores(),
        "coletas": coletas(),
        "testes": testes_funcionais(completo) if funcionais else [],
        "auditoria": audit.collect("/", Workspace().models_dirs),
    }


def texto(d: Dict) -> str:
    s = d["sistema"]
    inst = " ".join(f"{k}={'sim' if v else 'não'}" for k, v in s["cpu_instrucoes"].items())
    linhas = [f"IA-Linux MiniVideo — diagnóstico de {d['gerado_em']}", "",
              f"Kernel {s['kernel']} · boot {s['boot']} · placa {s['placa']['board_vendor']} {s['placa']['board_name']}"
              f" · BIOS {s['placa']['bios_version']} ({s['placa']['bios_date']})",
              f"CPU: {inst}", f"Linha do kernel: {s['cmdline']}", "", "RESUMO DOS TESTES"]
    for t in d["testes"]:
        linhas.append(f"  [{t['resultado']:<7}] {t['teste']} ({t['segundos']} s)")
    linhas += ["", "PLACAS DE VÍDEO"]
    for p in d["placas_de_video"]:
        linhas.append(f"  {p['card']}: {p['vendor']}:{p['device']} driver={p['driver']} vram={p['vram_total']} "
                      f"vbios={p['vbios']}")
    linhas += ["", "SENSORES (somente leitura)"]
    for x in d["sensores"] or [{"id": "nenhum", "metricas": {}, "avisos": []}]:
        linhas.append(f"  {x['id']}: " + ", ".join(f"{k}={v}" for k, v in x["metricas"].items()))
    for nome, c in d["coletas"].items():
        linhas += ["", f"== {nome}: {c['cmd']} (código {c['codigo']})", c["saida"].rstrip()]
    for t in d["testes"]:
        if t["resultado"] != OK:
            linhas += ["", f"== teste {t['teste']}: {t['cmd']}", t["saida"].rstrip()]
    linhas += ["", "== auditoria", audit.render_text(d["auditoria"])]
    return "\n".join(linhas) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="minivideo-diagnostico", description=__doc__.split("\n")[0])
    p.add_argument("--relatorio", action="store_true", help="grava Logs/diagnostico-<data>.txt e .json")
    p.add_argument("--completo", action="store_true", help="inclui llama-bench (se houver .gguf); mais lento")
    p.add_argument("--sem-testes", action="store_true", help="só coleta, sem testes funcionais")
    p.add_argument("--workspace")
    a = p.parse_args(argv)
    d = montar(a.completo, not a.sem_testes)
    t = texto(d)
    if not a.relatorio:
        print(t)
        return 0
    ws = Workspace(a.workspace)
    base = os.path.join(ws.logs, time.strftime("diagnostico-%Y%m%d-%H%M%S"))
    with open(base + ".txt", "w", encoding="utf-8") as fh:
        fh.write(t)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2, default=str)
    falhas = [x["teste"] for x in d["testes"] if x["resultado"] == FALHOU]
    print(f"Relatório: {base}.txt (e .json)")
    print("Testes com falha: " + (", ".join(falhas) if falhas else "nenhum"))
    print("Para enviar: copie os dois arquivos para um pendrive (tecla S abre um shell).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
