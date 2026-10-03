"""Utilitários de vídeo baseados em ffmpeg (multiplataforma via imageio-ffmpeg)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)


class VideoError(RuntimeError):
    """Erro ao processar vídeo com ffmpeg."""


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """Caminho do ffmpeg: usa o binário embutido do imageio-ffmpeg ou o do sistema."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 — qualquer falha cai no ffmpeg do sistema
        exe = shutil.which("ffmpeg")
        if not exe:
            raise VideoError("ffmpeg não encontrado. Instale com: pip install imageio-ffmpeg")
        return exe


def run_ffmpeg(args: list[str]) -> str:
    """Executa o ffmpeg e retorna o stderr (onde o ffmpeg escreve as informações)."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", *args]
    log.debug("ffmpeg %s", " ".join(args))
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-6:])
        raise VideoError(f"ffmpeg falhou:\n{tail}")
    return proc.stderr


def probe(path: Path) -> dict:
    """Lê duração, fps, resolução e presença de áudio (sem depender do ffprobe)."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, errors="replace",
    )
    info = proc.stderr
    result: dict = {"duration": 0.0, "fps": 0.0, "width": 0, "height": 0, "has_audio": False}
    if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", info):
        h, mnt, s = m.groups()
        result["duration"] = int(h) * 3600 + int(mnt) * 60 + float(s)
    if m := re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", info):
        result["width"], result["height"] = int(m.group(1)), int(m.group(2))
    if m := re.search(r"([\d.]+) fps", info):
        result["fps"] = float(m.group(1))
    result["has_audio"] = "Audio:" in info
    return result


def extract_frame(video: Path, time_s: float, out: Path) -> Path:
    """Extrai um frame no instante ``time_s`` (use valor negativo para contar do fim)."""
    seek = ["-sseof", str(time_s)] if time_s < 0 else ["-ss", f"{time_s:.3f}"]
    run_ffmpeg([*seek, "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)])
    if not out.exists():
        raise VideoError(f"Não foi possível extrair frame em {time_s:.2f}s de {video.name}")
    return out


def extract_keyframes(video: Path, times: list[float], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = probe(video)["duration"]
    frames = []
    for i, t in enumerate(times):
        # O último frame é pego a partir do fim para não "passar" da duração real.
        when = -0.05 if t >= duration - 0.05 else t
        frames.append(extract_frame(video, when, out_dir / f"key_{i:03d}.png"))
    return frames


def make_thumbnail(video: Path, out: Path) -> Path | None:
    try:
        return extract_frame(video, 0.0, out)
    except VideoError as exc:
        log.warning("Miniatura não gerada: %s", exc)
        return None


def ensure_audio(video: Path, out: Path) -> Path:
    """Garante uma trilha de áudio (silêncio, se necessário) — exigido pela concatenação."""
    if probe(video)["has_audio"]:
        return video
    run_ffmpeg([
        "-i", str(video), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest", "-c:v", "copy", "-c:a", "aac", str(out),
    ])
    return out


def concat_videos(clips: list[Path], out: Path, fps: int) -> Path:
    """Concatena clipes (re-encodando para uniformizar resolução, fps e áudio)."""
    if len(clips) == 1:
        shutil.copyfile(clips[0], out)
        return out
    work = out.parent
    normalized = [ensure_audio(c, work / f"{c.stem}_a.mp4") for c in clips]
    first = probe(normalized[0])
    w, h = first["width"] or 576, first["height"] or 1024
    inputs: list[str] = []
    filters: list[str] = []
    for i, clip in enumerate(normalized):
        inputs += ["-i", str(clip)]
        filters.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1[v{i}];"
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]"
        )
    streams = "".join(f"[v{i}][a{i}]" for i in range(len(normalized)))
    graph = ";".join(filters) + f";{streams}concat=n={len(normalized)}:v=1:a=1[v][a]"
    run_ffmpeg([
        *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", str(out),
    ])
    return out


def trim(video: Path, start: float, duration: float, out: Path) -> Path:
    run_ffmpeg([
        "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    ])
    return out


def export_vertical(video: Path, out: Path, width: int, height: int, fps: int | None = None) -> Path:
    """Exporta em MP4 9:16 (H.264 + AAC), com upscale Lanczos e crop central.

    ``fps`` permite reamostrar (ex.: 12 fps para o efeito stop-motion).
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1"
    )
    if fps:
        vf += f",fps={fps}"
    audio = ["-c:a", "aac", "-b:a", "192k"] if probe(video)["has_audio"] else ["-an"]
    run_ffmpeg([
        "-i", str(video), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", *audio, str(out),
    ])
    return out
