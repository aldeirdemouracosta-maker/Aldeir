"""Montagem final com FFmpeg: normaliza os clipes/imagens dos shots e concatena em um MP4."""
from __future__ import annotations

import os
import shutil
import subprocess

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class EditError(RuntimeError):
    pass


def usable_inputs(paths: list[str | None]) -> list[str] | None:
    """Lista de arquivos reais, na ordem dos shots; None se algum shot não tem arquivo (modo simulado)."""
    if not paths or not all(p and os.path.isfile(p) for p in paths):
        return None
    return list(paths)  # type: ignore[arg-type]


def validate(path: str) -> None:
    """ffprobe rejeita arquivos corrompidos antes da montagem (o ffmpeg entra em loop com -loop 1)."""
    if not shutil.which("ffprobe"):
        raise EditError("ffprobe não encontrado no PATH")
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_type", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditError(f"ffprobe: {exc}") from exc
    if r.returncode != 0 or "video" not in r.stdout:
        raise EditError(f"arquivo de mídia inválido ou sem vídeo: {path}")


def build_command(inputs: list[str], out_path: str, *, audio: str | None = None, width: int = 1280,
                  height: int = 720, fps: int = 24, image_seconds: float = 2.0) -> list[str]:
    cmd = ["ffmpeg", "-y", "-xerror", "-loglevel", "error"]
    for p in inputs:
        if os.path.splitext(p)[1].lower() in IMAGE_EXT:
            cmd += ["-loop", "1", "-t", str(image_seconds)]
        cmd += ["-i", p]
    if audio:
        cmd += ["-i", audio]
    chains = [
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{i}]"
        for i in range(len(inputs))
    ]
    joined = "".join(f"[v{i}]" for i in range(len(inputs)))
    chains.append(f"{joined}concat=n={len(inputs)}:v=1:a=0[outv]")
    cmd += ["-filter_complex", ";".join(chains), "-map", "[outv]"]
    if audio:
        cmd += ["-map", f"{len(inputs)}:a", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", out_path]
    return cmd


def assemble(inputs: list[str], out_path: str, *, audio: str | None = None, **kw) -> str:
    if not shutil.which("ffmpeg"):
        raise EditError("ffmpeg não encontrado no PATH")
    if audio and not os.path.isfile(audio):
        audio = None
    for p in inputs:
        validate(p)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp = f"{os.path.splitext(out_path)[0]}.partial.mp4"  # só vira o destino final se tudo der certo
    try:
        r = subprocess.run(build_command(inputs, tmp, audio=audio, **kw),
                           capture_output=True, text=True, timeout=600 + 300 * len(inputs), check=False)
        if r.returncode != 0 or not os.path.isfile(tmp):
            raise EditError(f"ffmpeg falhou (código {r.returncode}): {r.stderr[-400:]}")
        os.replace(tmp, out_path)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditError(f"ffmpeg: {exc}") from exc
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return out_path
