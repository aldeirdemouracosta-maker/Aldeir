"""Detecção de tipo por assinatura (magic bytes) e escrita de WAV com a biblioteca padrão."""
from __future__ import annotations

import array
import wave
from pathlib import Path
from typing import Sequence


def sniff_image(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def sniff_audio(head: bytes) -> str | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


def write_wav(path: Path, samples: Sequence[float], rate: int) -> None:
    """Grava amostras float [-1, 1] como WAV PCM 16 bits mono."""
    if rate <= 0 or not samples:
        raise ValueError("áudio vazio ou taxa inválida")
    pcm = array.array("h", (int(max(-1.0, min(1.0, float(s))) * 32767) for s in samples))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())

