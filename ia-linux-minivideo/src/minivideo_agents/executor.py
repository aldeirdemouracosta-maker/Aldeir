"""Executor de planos: cada etapa vira comandos locais (FFmpeg, NCNN, whisper.cpp).

- Uma pasta por job em ``Jobs/<job_id>/``; log JSONL em ``Logs/<job_id>.agentes.jsonl``.
- Etapas em GPU rodam sob o Hardware Safety Guard quando há sensores.
- O plano só roda se todas as etapas estiverem disponíveis.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from minivideo_guard.actions import ActionDispatcher, ProcessJobControl
from minivideo_guard.monitor import GuardMonitor, JobLog
from minivideo_guard.policy import GuardPolicy
from minivideo_guard.sensors import AmdgpuSysfsBackend, NvidiaSmiBackend

from .planner import Plan, Step, first_unavailable
from .registry import Assignment, find_weights
from .workspace import Workspace


class JobError(RuntimeError):
    pass


@dataclass
class JobResult:
    job_id: str
    saida: Optional[str]
    ok: bool
    etapas: List[Dict] = field(default_factory=list)
    erro: Optional[str] = None


def probe(path: str) -> Dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise JobError(f"ffprobe não conseguiu ler {path}: {out.stderr.strip()[:300]}")
    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = None
    if video and video.get("r_frame_rate", "0/0") != "0/0":
        n, d = video["r_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else None
    return {"video": video, "audio": audio, "fps": fps,
            "altura": int(video["height"]) if video else None,
            "duracao": float(data.get("format", {}).get("duration", 0) or 0)}


def ffmpeg_has(kind: str, name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", f"-{kind}"], capture_output=True, text=True, check=False)
    return re.search(rf"\s{re.escape(name)}\s", out.stdout) is not None


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


ENC_INTER = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]

LIMITES_PADRAO = {
    "tempo_max_etapa_s": 3 * 3600.0,
    "tempo_max_job_s": 8 * 3600.0,
    "memoria_max_mib": 12 * 1024.0,     # 16 GB na máquina X79: deixa folga ao sistema
    "disco_reserva_mib": 2048.0,
    "altura_max_gpu_vulkan_sw": 480,
}


def tree_rss_mib(pid: int) -> float:
    """Soma o RSS do processo e de todos os descendentes (via /proc)."""
    children: Dict[int, List[int]] = {}
    rss: Dict[int, int] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
            ppid, rss_pages = int(fields[1]), int(fields[21])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(int(entry))
        rss[int(entry)] = rss_pages
    total, stack = 0, [pid]
    while stack:
        p = stack.pop()
        total += rss.get(p, 0)
        stack.extend(children.get(p, []))
    return total * os.sysconf("SC_PAGE_SIZE") / 1048576


def free_mib(path: str) -> float:
    try:
        return shutil.disk_usage(path).free / 1048576
    except OSError:
        return float("inf")


class Executor:
    def __init__(self, ws: Workspace, assignments: Dict[str, Assignment], guard: bool = True,
                 guard_config: Optional[Dict] = None, sysfs_root: str = "/sys", prefer_vaapi: bool = True,
                 limites: Optional[Dict] = None):
        self.ws = ws
        self.assignments = assignments
        self.guard = guard
        self.guard_config = guard_config
        self.sysfs_root = sysfs_root
        self.prefer_vaapi = prefer_vaapi
        self.limites = dict(LIMITES_PADRAO, **(limites or {}))

    # ---------------- infraestrutura ----------------

    def _guard_pair(self, device_id: str):
        for backend in (AmdgpuSysfsBackend(self.sysfs_root), NvidiaSmiBackend()):
            for dev in backend.discover():
                if dev.id == device_id:
                    return backend, dev
        return None

    def _run(self, cmd: List[str], step: str, device_id: Optional[str]) -> None:
        """Executa um comando (lista de argumentos, nunca shell) sob os limites do job.

        A cada 0,5 s confere: tempo da etapa, prazo do job, memória (RSS da árvore
        de processos) e reserva de disco; em etapa de GPU, o Safety Guard a cada 2 s.
        """
        self.log.write("comando", etapa=step, cmd=cmd, dispositivo=device_id)
        lim = self.limites
        pair = self._guard_pair(device_id) if (self.guard and device_id and device_id != "cpu") else None
        started = time.time()
        errpath = os.path.join(self.job_dir, f"{step}.stderr.log")
        motivo_parada = None
        with open(errpath, "w") as errf:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=errf, start_new_session=True)
            ctl = ProcessJobControl(proc, grace=5)
            dispatcher = ActionDispatcher(ctl) if pair else None
            mon = (GuardMonitor(pair[0], pair[1], GuardPolicy(self.guard_config), dispatcher,
                                JobLog(self.ws.logs, self.job_id), interval=2.0) if pair else None)
            next_guard = 0.0
            while proc.poll() is None:
                now = time.time()
                if mon and now >= next_guard:
                    mon.step()
                    next_guard = now + mon.interval
                    if dispatcher.stopped:
                        motivo_parada = "encerrado pelo Safety Guard (condição crítica)"
                        break
                paused = bool(dispatcher and dispatcher.paused)
                if not paused and now - started > lim["tempo_max_etapa_s"]:
                    motivo_parada = f"tempo da etapa excedido ({lim['tempo_max_etapa_s']:.0f} s)"
                elif not paused and now > self.deadline:
                    motivo_parada = f"tempo do job excedido ({lim['tempo_max_job_s']:.0f} s)"
                elif tree_rss_mib(proc.pid) > lim["memoria_max_mib"]:
                    motivo_parada = f"memória acima do limite ({lim['memoria_max_mib']:.0f} MiB)"
                elif free_mib(self.job_dir) < lim["disco_reserva_mib"]:
                    motivo_parada = f"disco abaixo da reserva ({lim['disco_reserva_mib']:.0f} MiB livres exigidos)"
                if motivo_parada:
                    ctl.stop(motivo_parada)
                    break
                time.sleep(0.5)
            rc = proc.wait()
        with open(errpath) as errf:
            err = errf.read()
        self.log.write("resultado", etapa=step, codigo=rc, segundos=round(time.time() - started, 2),
                       parada=motivo_parada)
        if motivo_parada:
            raise JobError(f"{step}: {motivo_parada}")
        if rc != 0:
            raise JobError(f"{step}: comando falhou (código {rc}): {err.strip()[-500:]}")

    def _tool(self, agent_id: str) -> str:
        return self.assignments[agent_id].ferramenta

    def _device(self, agent_id: str) -> Optional[str]:
        dev = self.assignments[agent_id].device
        return dev.id if dev else None

    def _out(self, n: int, name: str) -> str:
        return os.path.join(self.job_dir, f"{n:02d}_{name}.mp4")

    def _frames(self, src: str, name: str) -> str:
        d = os.path.join(self.job_dir, name)
        os.makedirs(d, exist_ok=True)
        self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-fps_mode", "passthrough", os.path.join(d, "%08d.png")],
                  f"extrair_{name}", None)
        return d

    def _assemble(self, frames: str, fps: float, audio_src: Optional[str], out: str, step: str,
                  vf: Optional[str] = None) -> None:
        cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", f"{fps:.6f}", "-i", os.path.join(frames, "%08d.png")]
        if audio_src:
            cmd += ["-i", audio_src, "-map", "0:v", "-map", "1:a?", "-c:a", "copy", "-shortest"]
        if vf:
            cmd += ["-vf", vf]
        self._run(cmd + ENC_INTER + [out], f"montar_{step}", None)

    # ---------------- etapas ----------------

    def _cortador(self, n, step, src, ctx):
        ini, fim = step.params["inicio"], step.params["fim"]
        dur = fim - ini
        out = self._out(n, "corte")
        audio = []
        if ctx["info"]["audio"]:
            # Fades de 50 ms nas bordas: sem clique no corte (quadros AAC vazam o trecho vizinho),
            # o que também deixa a normalização de loudness chegar ao alvo.
            f = min(0.05, dur / 4)
            audio = ["-af", f"afade=t=in:d={f:.3f},afade=t=out:st={max(dur - f, 0):.3f}:d={f:.3f}",
                     "-c:a", "aac", "-b:a", "192k"]
        self._run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-i", src, "-t", f"{dur:.3f}",
                   *ENC_INTER, *audio, out], "cortador", "cpu")
        return out

    def _silencios(self, n, step, src, ctx):
        out = self._out(n, "sem_silencios")
        self._run([self._tool("silencios"), src, "--margin", f"{step.params.get('margem_s', 0.2)}s",
                   "--no-open", "-o", out], "silencios", "cpu")
        return out

    LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"

    def _medir_loudnorm(self, src: str, pre: List[str]) -> Optional[Dict]:
        """1ª passada do loudnorm: mede a entrada (JSON no stderr)."""
        out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn", "-af",
                              ",".join(pre + [self.LOUDNORM + ":print_format=json"]), "-f", "null", "-"],
                             capture_output=True, text=True, timeout=self.limites["tempo_max_etapa_s"], check=False)
        ini, fim = out.stderr.rfind("{"), out.stderr.rfind("}")
        if out.returncode != 0 or ini < 0:
            raise JobError(f"audio: medição de loudness falhou: {out.stderr.strip()[-300:]}")
        m = json.loads(out.stderr[ini:fim + 1])
        return None if m["input_i"] in ("-inf", "inf") else m

    def _audio(self, n, step, src, ctx):
        if not ctx["info"]["audio"]:
            ctx["notas"].append("audio: vídeo sem trilha de áudio, etapa ignorada")
            return src
        pre = ["afftdn=nf=-25"] if step.params.get("reduzir_ruido", True) else []
        filtros = list(pre)
        if step.params.get("normalizar", True):
            # Duas passadas (medir, depois ganho linear): exato também em trechos curtos,
            # onde o modo dinâmico de passada única não chega ao alvo.
            m = self._medir_loudnorm(src, pre)
            if m is None:
                ctx["notas"].append("audio: trilha silenciosa, normalização ignorada")
            else:
                filtros.append(f"{self.LOUDNORM}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                               f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                               f"offset={m['target_offset']}:linear=true")
        if not filtros:
            return src
        out = self._out(n, "audio")
        self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "copy", "-af", ",".join(filtros),
                   "-ar", "48000", "-c:a", "aac", "-b:a", "192k", out], "audio", "cpu")
        return out

    def _cenas(self, n, step, src, ctx):
        limiar = step.params.get("limiar", 0.4)
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-vf", f"select='gt(scene,{limiar})',showinfo",
                               "-f", "null", "-"], capture_output=True, text=True, check=False)
        self.log.write("resultado", etapa="cenas", codigo=proc.returncode)
        if proc.returncode != 0:
            raise JobError(f"cenas: ffmpeg falhou: {proc.stderr[-300:]}")
        tempos = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
        csv = os.path.join(self.job_dir, "cenas.csv")
        with open(csv, "w") as fh:
            fh.write("cena,inicio_s\n1,0.000\n")
            for i, t in enumerate(tempos, 2):
                fh.write(f"{i},{t:.3f}\n")
        ctx["artefatos"]["cenas"] = csv
        return src

    def _interpolador(self, n, step, src, ctx):
        fator = int(step.params.get("fator", 2))
        weights = find_weights(self.assignments["interpolador"].agent, self.ws.models_dirs)
        model_dir = os.path.dirname(weights[0])
        frames_in = self._frames(src, "quadros_rife_in")
        total = len(os.listdir(frames_in))
        frames_out = os.path.join(self.job_dir, "quadros_rife_out")
        os.makedirs(frames_out, exist_ok=True)
        self._run([self._tool("interpolador"), "-i", frames_in, "-o", frames_out, "-m", model_dir,
                   "-n", str(total * fator), "-f", "%08d.png"], "interpolador", self._device("interpolador"))
        fps = ctx["info"]["fps"] or 30.0
        out = self._out(n, "interpolado")
        if step.params.get("camera_lenta"):
            self._assemble(frames_out, fps, None, out, "interpolador")
            ctx["notas"].append("câmera lenta: áudio removido (duração mudou)")
        else:
            self._assemble(frames_out, fps * fator, src, out, "interpolador")
        return out

    def _upscaler(self, n, step, src, ctx):
        altura = int(step.params.get("altura", 1080))
        weights = find_weights(self.assignments["upscaler"].agent, self.ws.models_dirs)
        model_dir = os.path.dirname(weights[0])
        names = {os.path.basename(w)[:-6] for w in weights}
        modelo = "realesr-animevideov3-x2" if "realesr-animevideov3-x2" in names else sorted(names)[0]
        escala = int(re.search(r"x(\d)", modelo).group(1)) if re.search(r"x(\d)", modelo) else 4
        frames_in = self._frames(src, "quadros_esrgan_in")
        frames_out = os.path.join(self.job_dir, "quadros_esrgan_out")
        os.makedirs(frames_out, exist_ok=True)
        self._run([self._tool("upscaler"), "-i", frames_in, "-o", frames_out, "-m", model_dir,
                   "-n", modelo.replace(f"-x{escala}", "") if modelo.startswith("realesr-animevideov3") else modelo,
                   "-s", str(escala), "-f", "png"], "upscaler", self._device("upscaler"))
        out = self._out(n, "upscale")
        self._assemble(frames_out, ctx["info"]["fps"] or 30.0, src, out, "upscaler",
                       vf=f"scale=-2:{altura}:flags=lanczos")
        return out

    def _escala(self, n, step, src, ctx):
        out = self._out(n, "escala")
        self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf",
                   f"scale=-2:{int(step.params.get('altura', 1080))}:flags=lanczos", *ENC_INTER, "-c:a", "copy", out],
                  "escala", "cpu")
        return out

    def _transcritor(self, n, step, src, ctx):
        if not ctx["info"]["audio"]:
            raise JobError("transcritor: vídeo sem áudio")
        wav = os.path.join(self.job_dir, "audio16k.wav")
        self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ar", "16000", "-ac", "1", wav], "extrair_audio", None)
        model = find_weights(self.assignments["transcritor"].agent, self.ws.models_dirs)[0]
        base = os.path.join(self.job_dir, "legenda")
        self._run([self._tool("transcritor"), "-m", model, "-f", wav, "-l", step.params.get("idioma", "pt"),
                   "-osrt", "-of", base], "transcritor", self._device("transcritor"))
        ctx["artefatos"]["srt"] = base + ".srt"
        return src

    def _legendas(self, n, step, src, ctx):
        srt = ctx["artefatos"].get("srt")
        if not srt or not os.path.exists(srt):
            raise JobError("legendas: nenhuma legenda SRT gerada antes")
        out = self._out(n, "legendado")
        if ffmpeg_has("filters", "subtitles"):
            self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", f"subtitles='{_escape_filter_path(srt)}'",
                       *ENC_INTER, "-c:a", "copy", out], "legendas", "cpu")
        else:
            self._run(["ffmpeg", "-y", "-v", "error", "-i", src, "-i", srt, "-map", "0", "-map", "1",
                       "-c", "copy", "-c:s", "mov_text", out], "legendas", "cpu")
            ctx["notas"].append("legendas: FFmpeg sem libass; legenda anexada como faixa (não queimada)")
        return out

    def _exportador(self, n, step, src, ctx, saida):
        crf = str(step.params.get("crf", 20))
        render = "/dev/dri/renderD128"
        amd = any(a.device and a.device.kind.startswith("vulkan") for a in self.assignments.values())
        if self.prefer_vaapi and amd and os.path.exists(render) and ffmpeg_has("encoders", "h264_vaapi"):
            cmd = ["ffmpeg", "-y", "-v", "error", "-vaapi_device", render, "-i", src,
                   "-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-bf", "0", "-qp", crf]
            ctx["notas"].append("exportado com VA-API (codificador da GPU)")
        else:
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "libx264", "-preset", "medium",
                   "-crf", crf, "-pix_fmt", "yuv420p"]
        self._run(cmd + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", saida], "exportador", "cpu")
        return saida

    # ---------------- plano ----------------

    def run(self, plan: Plan, entrada: str, saida: str, job_id: Optional[str] = None,
            limpar_quadros: bool = True) -> JobResult:
        self.job_id = job_id or time.strftime("job-%Y%m%d-%H%M%S")
        self.job_dir = os.path.join(self.ws.jobs, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)
        self.deadline = time.time() + self.limites["tempo_max_job_s"]
        self.log = JobLog(self.ws.logs, self.job_id, suffix="agentes")
        result = JobResult(self.job_id, None, False)
        blocked = first_unavailable(plan, self.assignments)
        if blocked:
            result.erro = f"etapa indisponível: {blocked}"
            self.log.write("recusado", motivo=result.erro)
            return result
        if not os.path.isfile(entrada):
            result.erro = f"entrada não existe: {entrada}"
            return result
        self.log.write("inicio", pedido=plan.pedido, entrada=entrada, saida=saida,
                       etapas=[s.to_dict() for s in plan.etapas])
        ctx = {"notas": [], "artefatos": {}}
        src = entrada
        try:
            for n, step in enumerate(plan.etapas, 1):
                ctx["info"] = probe(src)
                t0 = time.time()
                if step.agente == "exportador":
                    src = self._exportador(n, step, src, ctx, saida)
                else:
                    src = getattr(self, f"_{step.agente}")(n, step, src, ctx)
                result.etapas.append({"agente": step.agente, "saida": src, "segundos": round(time.time() - t0, 2)})
            result.ok, result.saida = True, saida
        except (JobError, OSError, KeyError, IndexError) as exc:
            result.erro = str(exc)
        finally:
            if limpar_quadros:
                for d in os.listdir(self.job_dir):
                    if d.startswith("quadros_"):
                        shutil.rmtree(os.path.join(self.job_dir, d), ignore_errors=True)
            self.log.write("fim", ok=result.ok, erro=result.erro, notas=ctx["notas"],
                           artefatos=ctx["artefatos"], etapas=result.etapas)
        result.etapas.append({"notas": ctx["notas"], "artefatos": ctx["artefatos"]})
        return result
