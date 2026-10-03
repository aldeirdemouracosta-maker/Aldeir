"""Backends de geração.

* ``ComfyBackend`` — o backend real: preenche um workflow JSON e o executa no ComfyUI.
* ``DemoBackend`` — gera vídeos sintéticos com ffmpeg. Permite testar a interface,
  a fila e os pipelines em qualquer máquina, sem GPU nem modelos.

Ambos implementam ``generate(kind, params, work_dir, on_progress) -> Path``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from .comfy_client import VIDEO_EXTS, ComfyClient, ComfyError, ComfyProgress
from .config import AppConfig
from .video_utils import run_ffmpeg
from .workflows import build_workflow, load_template

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, str, Image.Image | None], None]


@dataclass
class GenParams:
    """Parâmetros de uma única chamada de modelo (um clipe)."""

    prompt: str
    negative: str
    width: int
    height: int
    seconds: float
    fps: int
    seed: int
    steps: int
    start_image: Path | None = None
    end_image: Path | None = None
    guidance: float = 10.0
    memory_preservation: float = 6.0
    with_audio: bool = False

    @property
    def ltx_length(self) -> int:
        """Número de frames no formato exigido pelo LTX (8·n + 1)."""
        frames = max(int(round(self.seconds * self.fps)), 9)
        return (frames - 1) // 8 * 8 + 1


class Backend(Protocol):
    name: str

    def generate(self, kind: str, params: GenParams, work_dir: Path, on_progress: ProgressFn) -> Path: ...

    def free_memory(self) -> None: ...

    def interrupt(self) -> None: ...


class ComfyBackend:
    """Executa os workflows de ``workflows/`` no ComfyUI local."""

    name = "ComfyUI"

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.client = ComfyClient(cfg.comfy_url, cfg.comfy_timeout)

    def _template_params(self, params: GenParams, work_dir: Path) -> dict[str, Any]:
        m = self.cfg.models
        upload = self.client.upload_image
        return {
            "prompt": params.prompt,
            "negative": params.negative,
            "width": params.width,
            "height": params.height,
            "seed": params.seed,
            "steps": params.steps,
            "fps": params.fps,
            "total_seconds": float(params.seconds),
            "length": params.ltx_length,
            "guidance": params.guidance,
            "gpu_memory_preservation": params.memory_preservation,
            "start_image": upload(params.start_image) if params.start_image else None,
            "end_image": upload(params.end_image) if params.end_image else None,
            "filename_prefix": f"frameltx/{work_dir.name}",
            "framepack_model": m.framepack,
            "framepack_clip_l": m.framepack_clip_l,
            "framepack_llama": m.framepack_llama,
            "framepack_clip_vision": m.framepack_clip_vision,
            "framepack_vae": m.framepack_vae,
            "ltx_checkpoint": m.ltx_checkpoint,
            "ltx_text_encoder": m.ltx_text_encoder,
        }

    def generate(self, kind: str, params: GenParams, work_dir: Path, on_progress: ProgressFn) -> Path:
        template = load_template(self.cfg.workflows_dir, kind)
        workflow = build_workflow(template, self._template_params(params, work_dir))
        log.info("Executando workflow '%s' (%d nós) %dx%d, %.1fs",
                 kind, len(workflow), params.width, params.height, params.seconds)

        def relay(p: ComfyProgress) -> None:
            on_progress(p.fraction, p.message, p.preview)

        files = self.client.run(workflow, work_dir / f"comfy_{kind}", relay)
        videos = [f for f in files if f.suffix.lower() in VIDEO_EXTS]
        if not videos:
            raise ComfyError(f"O workflow '{kind}' não gerou vídeo (arquivos: {[f.name for f in files]}).")
        return videos[0]

    def free_memory(self) -> None:
        self.client.free_memory()

    def interrupt(self) -> None:
        self.client.interrupt()


class DemoBackend:
    """Gera vídeos de demonstração (zoom suave na imagem + tom de áudio) via ffmpeg."""

    name = "Demonstração"

    def __init__(self, step_delay: float = 0.15) -> None:
        self.step_delay = step_delay
        self._interrupted = False

    def generate(self, kind: str, params: GenParams, work_dir: Path, on_progress: ProgressFn) -> Path:
        self._interrupted = False
        preview = Image.open(params.start_image).convert("RGB") if params.start_image else None
        for step in range(1, 6):
            if self._interrupted:
                raise ComfyError("Geração interrompida.")
            time.sleep(self.step_delay)
            on_progress(step / 6, f"[demo] Passo {step}/5 ({kind})", preview)

        out = work_dir / f"demo_{kind}_{time.time_ns()}.mp4"
        w, h, fps, dur = params.width, params.height, params.fps, max(params.seconds, 0.5)
        frames = max(int(dur * fps), 2)
        if params.start_image:
            video_in = ["-loop", "1", "-i", str(params.start_image)]
            vf = (
                f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                f"zoompan=z='min(1+on/{frames}*0.25,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={w}x{h}:fps={fps},format=yuv420p[v]"
            )
        else:
            video_in = ["-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={fps}"]
            vf = "[0:v]hue=h=t*40,format=yuv420p[v]"
        audio_in = ["-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={dur}"]
        audio_map = ["-map", "1:a", "-c:a", "aac"] if params.with_audio else []
        run_ffmpeg([
            *video_in, *(audio_in if params.with_audio else []),
            "-filter_complex", vf, "-map", "[v]", *audio_map,
            "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "ultrafast", str(out),
        ])
        return out

    def free_memory(self) -> None:
        log.info("[demo] memória liberada")

    def interrupt(self) -> None:
        self._interrupted = True


def make_backend(cfg: AppConfig) -> Backend:
    return DemoBackend() if cfg.demo_mode else ComfyBackend(cfg)
