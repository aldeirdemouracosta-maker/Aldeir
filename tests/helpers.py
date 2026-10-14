"""Auxiliares de teste (não fazem parte do app)."""
import math
import wave
from pathlib import Path

from fastapi.testclient import TestClient


def client(app) -> TestClient:
    """TestClient com Host de loopback real (o app não aceita 'testserver')."""
    return TestClient(app, base_url="http://127.0.0.1:8000")


def sine(seconds: float = 0.2, rate: int = 16000, hz: float = 440.0) -> list[float]:
    return [0.5 * math.sin(2 * math.pi * hz * i / rate) for i in range(int(seconds * rate))]


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        return {"rate": w.getframerate(), "channels": w.getnchannels(),
                "seconds": w.getnframes() / w.getframerate()}
