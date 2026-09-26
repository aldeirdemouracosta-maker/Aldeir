"""
FalaVox (F2) — o aluno responde com a voz.

Fluxo: gravar do microfone -> transcrever com Whisper local -> tela de
confirmação (Enter confirma, Espaço grava de novo, Esc cancela) -> o texto
vai para o Mini Caderno, para a área de transferência e para o arquivo de
respostas, que pode ser aberto no editor do DOSVOX.

Dependências opcionais (o resto do IAVOX funciona sem elas):
    pip install sounddevice soundfile faster-whisper
"""
from __future__ import annotations

import threading
import wave
from datetime import datetime
from pathlib import Path

TAXA = 16000  # o Whisper trabalha em 16 kHz mono
MODELO_WHISPER_PADRAO = "small"  # bom equilíbrio para português em CPU


def gravacao_disponivel() -> bool:
    try:
        import sounddevice  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def transcricao_disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class Gravador:
    """Grava do microfone até `parar()` ser chamado (ou até max_segundos)."""

    def __init__(self, max_segundos: int = 120):
        self.max_segundos = max_segundos
        self._parar = threading.Event()
        self._blocos: list = []

    def parar(self) -> None:
        self._parar.set()

    def gravar(self, destino: str | Path) -> Path:
        import numpy as np
        import sounddevice as sd

        self._parar.clear()
        self._blocos = []

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            self._blocos.append(indata.copy())

        with sd.InputStream(samplerate=TAXA, channels=1, dtype="int16", callback=callback):
            self._parar.wait(timeout=self.max_segundos)

        audio = np.concatenate(self._blocos) if self._blocos else np.zeros((0, 1), dtype="int16")
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destino), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(TAXA)
            w.writeframes(audio.tobytes())
        return destino


class Transcritor:
    """Whisper local via faster-whisper. O modelo é baixado na primeira vez e depois fica offline."""

    def __init__(self, modelo: str = MODELO_WHISPER_PADRAO):
        self.modelo_nome = modelo
        self._modelo = None

    def transcrever(self, wav: str | Path) -> str:
        if self._modelo is None:
            from faster_whisper import WhisperModel

            self._modelo = WhisperModel(self.modelo_nome, device="cpu", compute_type="int8")
        segmentos, _info = self._modelo.transcribe(str(wav), language="pt", vad_filter=True)
        return " ".join(s.text.strip() for s in segmentos).strip()


def inserir_resposta(texto: str, arquivo: str | Path | None = None) -> Path:
    """Acrescenta a resposta confirmada ao arquivo de respostas (lido pelo EDIVOX)."""
    import platform

    arquivo = Path(arquivo) if arquivo else Path.home() / "IAVOX_respostas.txt"
    encoding = "cp1252" if platform.system() == "Windows" else "utf-8"
    with arquivo.open("a", encoding=encoding, errors="replace") as f:
        f.write(f"[{datetime.now():%d/%m/%Y %H:%M}] {texto.strip()}\n")
    return arquivo
