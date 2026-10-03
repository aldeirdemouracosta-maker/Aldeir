"""Os três modos de geração: FramePack, LTX e Combinado.

Cada modo recebe um ``GenerationRequest`` e um ``PipelineContext`` (backend,
armazenamento, callback de progresso) e devolve o caminho do vídeo final.
Toda falta de VRAM é tratada aqui: o perfil de qualidade é reduzido e a
etapa é repetida automaticamente.
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from PIL import Image

from . import video_utils as vu
from .backends import Backend, GenParams
from .comfy_client import ComfyError, ComfyOOMError
from .config import AppConfig
from .presets import PRESETS, build_prompts
from .storage import HistoryEntry, Storage, new_entry_id
from .vram import QualityProfile, lower_profile

log = logging.getLogger(__name__)

T = TypeVar("T")

MODES = {
    "framepack": "FramePack — vídeo longo, pouca VRAM",
    "ltx": "LTX — qualidade + áudio",
    "combinado": "Vídeo Longo + Qualidade (FramePack → LTX)",
}
DURATIONS = (5, 10, 15, 30, 60)


class UserFacingError(RuntimeError):
    """Erro com mensagem pronta para ser mostrada ao usuário."""


class CancelledError(RuntimeError):
    pass


@dataclass
class GenerationRequest:
    mode: str
    prompt: str
    preset: str = "Livre"
    style: str = "Realista"
    duration_s: int = 5
    ltx_variant: str = "t2v"  # "t2v" ou "i2v" (no modo LTX)
    start_image: Path | None = None
    end_image: Path | None = None
    seed: int = -1
    export_hd: bool = True

    def resolved_seed(self) -> int:
        return self.seed if self.seed >= 0 else random.randint(0, 2**31 - 1)


ProgressEmit = Callable[[float, str, Image.Image | None], None]


@dataclass
class PipelineContext:
    backend: Backend
    storage: Storage
    cfg: AppConfig
    profile: QualityProfile
    emit: ProgressEmit
    is_cancelled: Callable[[], bool] = lambda: False
    notes: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        """Aviso que aparece no log da interface e é salvo no histórico."""
        log.warning(message)
        self.notes.append(message)
        self.emit(-1, message, None)

    def check_cancel(self) -> None:
        if self.is_cancelled():
            raise CancelledError("Geração cancelada pelo usuário.")


class Span:
    """Mapeia o progresso de uma etapa (0..1) para uma fatia da barra total."""

    def __init__(self, ctx: PipelineContext, start: float, end: float, label: str) -> None:
        self.ctx, self.start, self.end, self.label = ctx, start, end, label

    def __call__(self, frac: float, msg: str, preview: Image.Image | None = None) -> None:
        self.ctx.check_cancel()
        overall = self.start + (self.end - self.start) * max(0.0, min(frac, 1.0))
        self.ctx.emit(overall, f"{self.label}: {msg}", preview)

    def split(self, index: int, count: int, label: str) -> Span:
        size = (self.end - self.start) / count
        return Span(self.ctx, self.start + size * index, self.start + size * (index + 1), label)


# ---------------------------------------------------------------- VRAM fallback

def with_vram_fallback(ctx: PipelineContext, step: Callable[[QualityProfile], T]) -> T:
    """Executa ``step`` e, se faltar VRAM, reduz a qualidade e tenta de novo."""
    profile = ctx.profile
    while True:
        try:
            return step(profile)
        except ComfyOOMError:
            ctx.backend.free_memory()
            smaller = lower_profile(profile)
            if smaller is None:
                raise UserFacingError(
                    "VRAM insuficiente mesmo na qualidade mínima. Feche outros programas que usam "
                    "a GPU (jogos, navegadores com aceleração) ou reduza a duração."
                ) from None
            ctx.note(f"⚠️ VRAM insuficiente, reduzindo qualidade: {profile.label} → {smaller.label}")
            profile = smaller
            ctx.profile = smaller  # próximas etapas já começam no perfil menor


# ---------------------------------------------------------------- etapas

def _framepack_clip(
    ctx: PipelineContext, req: GenerationRequest, prompt: str, negative: str, seed: int,
    seconds: float, work: Path, span: Span,
) -> Path:
    preset = PRESETS.get(req.preset, PRESETS["Livre"])

    def step(p: QualityProfile) -> Path:
        params = GenParams(
            prompt=prompt, negative=negative, width=p.fp_width, height=p.fp_height,
            seconds=seconds, fps=p.fp_fps, seed=seed, steps=p.fp_steps,
            start_image=req.start_image, end_image=req.end_image,
            guidance=preset.motion_guidance, memory_preservation=p.fp_memory_preservation,
        )
        return ctx.backend.generate("framepack", params, work, span)

    return with_vram_fallback(ctx, step)


def _ltx_clip(
    ctx: PipelineContext, kind: str, prompt: str, negative: str, seed: int, seconds: float,
    work: Path, span: Span, start: Path | None = None, end: Path | None = None,
) -> Path:
    def step(p: QualityProfile) -> Path:
        params = GenParams(
            prompt=prompt, negative=negative, width=p.ltx_width, height=p.ltx_height,
            seconds=min(seconds, p.ltx_max_seconds), fps=p.ltx_fps, seed=seed, steps=p.ltx_steps,
            start_image=start, end_image=end, with_audio=True,
        )
        return ctx.backend.generate(kind, params, work, span)

    return with_vram_fallback(ctx, step)


def _segment_lengths(total: float, max_len: float) -> list[float]:
    count = max(1, math.ceil(total / max_len - 1e-6))
    return [total / count] * count


# ---------------------------------------------------------------- modos

def run_framepack(ctx: PipelineContext, req: GenerationRequest, seed: int, work: Path) -> Path:
    if not req.start_image:
        raise UserFacingError("O modo FramePack precisa de uma imagem inicial.")
    prompt, negative = build_prompts(req.prompt, req.preset, req.style)
    return _framepack_clip(ctx, req, prompt, negative, seed, req.duration_s, work,
                           Span(ctx, 0.0, 0.9, "FramePack"))


def run_ltx(ctx: PipelineContext, req: GenerationRequest, seed: int, work: Path) -> Path:
    """LTX puro. Durações maiores que o limite do perfil são encadeadas:
    o último frame de cada clipe vira a imagem inicial do próximo."""
    prompt, negative = build_prompts(req.prompt, req.preset, req.style)
    use_image = req.ltx_variant == "i2v"
    if use_image and not req.start_image:
        raise UserFacingError("Image-to-Video precisa de uma imagem. Envie uma imagem ou use Text-to-Video.")

    segments = _segment_lengths(req.duration_s, ctx.profile.ltx_max_seconds)
    if len(segments) > 1:
        ctx.note(f"ℹ️ {req.duration_s}s excede o limite do LTX neste perfil; "
                 f"gerando {len(segments)} clipes encadeados.")
    total = Span(ctx, 0.0, 0.85, "LTX")
    clips: list[Path] = []
    start = req.start_image if use_image else None
    for i, seconds in enumerate(segments):
        span = total.split(i, len(segments), f"LTX clipe {i + 1}/{len(segments)}")
        kind = "ltx_i2v" if start else "ltx_t2v"
        clip = _ltx_clip(ctx, kind, prompt, negative, seed + i, seconds, work, span, start=start)
        clips.append(clip)
        if i < len(segments) - 1:
            start = vu.extract_frame(clip, -0.05, work / f"chain_{i:02d}.png")
    ctx.emit(0.88, "Juntando clipes…", None)
    return vu.concat_videos(clips, work / "ltx_joined.mp4", ctx.profile.ltx_fps)


def run_combined(ctx: PipelineContext, req: GenerationRequest, seed: int, work: Path) -> Path:
    """FramePack gera o movimento longo; o LTX refina cada trecho usando os
    frames-chave como primeiro/último frame e adiciona áudio sincronizado."""
    if not req.start_image:
        raise UserFacingError("O modo Combinado precisa de uma imagem inicial.")
    prompt, negative = build_prompts(req.prompt, req.preset, req.style)

    base = _framepack_clip(ctx, req, prompt, negative, seed, req.duration_s, work,
                           Span(ctx, 0.0, 0.4, "Etapa 1/3 FramePack"))
    ctx.backend.free_memory()  # descarrega o FramePack antes de carregar o LTX

    duration = vu.probe(base)["duration"] or float(req.duration_s)
    segments = _segment_lengths(duration, ctx.profile.ltx_max_seconds)
    times = [sum(segments[:i]) for i in range(len(segments) + 1)]
    ctx.emit(0.42, f"Etapa 2/3: extraindo {len(times)} frames-chave", None)
    keys = vu.extract_keyframes(base, times, work / "keys")

    refine = Span(ctx, 0.45, 0.88, "Etapa 3/3 LTX")
    clips: list[Path] = []
    for i, seconds in enumerate(segments):
        span = refine.split(i, len(segments), f"Etapa 3/3 LTX trecho {i + 1}/{len(segments)}")
        try:
            clip = _ltx_clip(ctx, "ltx_flf", prompt, negative, seed + i, seconds, work, span,
                             start=keys[i], end=keys[i + 1])
        except (ComfyError, UserFacingError) as exc:
            if isinstance(exc, ComfyError) and "interrompida" in str(exc):
                raise
            ctx.note(f"⚠️ Trecho {i + 1} não pôde ser refinado ({exc}); usando versão FramePack.")
            clip = vu.trim(base, times[i], seconds, work / f"fallback_{i:02d}.mp4")
        clips.append(clip)
    ctx.emit(0.88, "Juntando trechos refinados…", None)
    return vu.concat_videos(clips, work / "combined.mp4", ctx.profile.ltx_fps)


RUNNERS: dict[str, Callable[[PipelineContext, GenerationRequest, int, Path], Path]] = {
    "framepack": run_framepack,
    "ltx": run_ltx,
    "combinado": run_combined,
}


def run_generation(ctx: PipelineContext, req: GenerationRequest) -> HistoryEntry:
    """Executa o modo escolhido, exporta em 9:16 e registra no histórico."""
    runner = RUNNERS.get(req.mode)
    if runner is None:
        raise UserFacingError(f"Modo desconhecido: {req.mode}")
    seed = req.resolved_seed()
    work = ctx.storage.new_work_dir()
    started = time.monotonic()
    log.info("Nova geração: modo=%s duração=%ss perfil=%s seed=%s",
             req.mode, req.duration_s, ctx.profile.key, seed)
    try:
        raw = runner(ctx, req, seed, work)
        ctx.emit(0.92, "Exportando MP4 9:16…", None)
        out_base = ctx.storage.new_output_base(req.mode, req.prompt or req.preset)
        preset = PRESETS.get(req.preset, PRESETS["Livre"])
        width, height = _export_size(ctx, req)
        final = vu.export_vertical(raw, out_base.with_suffix(".mp4"), width, height, preset.post_fps)
        thumb = vu.make_thumbnail(final, out_base.with_suffix(".jpg"))
        entry = HistoryEntry(
            id=new_entry_id(), created_at=time.strftime("%Y-%m-%dT%H:%M:%S"), mode=req.mode,
            prompt=req.prompt, preset=req.preset, style=req.style, duration_s=req.duration_s,
            profile=ctx.profile.key, seed=seed, video_path=str(final),
            thumbnail_path=str(thumb) if thumb else None,
            elapsed_s=round(time.monotonic() - started, 1), notes=list(ctx.notes),
        )
        ctx.storage.add_entry(entry)
        ctx.emit(1.0, "✅ Vídeo pronto!", None)
        return entry
    except vu.VideoError as exc:
        raise UserFacingError(f"Erro ao processar o vídeo: {exc}") from exc
    finally:
        ctx.storage.cleanup(work)


def _export_size(ctx: PipelineContext, req: GenerationRequest) -> tuple[int, int]:
    if req.export_hd:
        return ctx.cfg.export_width, ctx.cfg.export_height
    p = ctx.profile
    return (p.fp_width, p.fp_height) if req.mode == "framepack" else (p.ltx_width, p.ltx_height)
