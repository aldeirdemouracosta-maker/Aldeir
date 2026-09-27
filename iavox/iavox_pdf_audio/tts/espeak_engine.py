"""
Motor de TTS 100% offline usando espeak-ng.
Robusto, leve, roda em qualquer máquina — voz robótica, mas sempre disponível.
Bom fallback final se nenhum outro motor estiver instalado.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from .base import TTSEngine

# Caminhos padrão de instalação no Windows (o instalador oficial usa um
# desses) — usados como fallback se o binário não estiver no PATH (comum
# logo após instalar, antes de abrir uma janela nova do terminal/app).
WINDOWS_DEFAULT_ESPEAK_PATHS = [
    r"C:\Program Files\eSpeak NG\espeak-ng.exe",
    r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
]


def _autodetect_espeak_binary() -> str | None:
    if platform.system() != "Windows":
        return None
    for candidate in WINDOWS_DEFAULT_ESPEAK_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


class EspeakEngine(TTSEngine):
    name = "espeak-ng (offline básico)"

    def __init__(self, voice: str = "pt-br", speed_wpm: int = 160, binary_path: str | None = None):
        self.voice = voice
        self.speed_wpm = speed_wpm
        if binary_path and Path(binary_path).exists():
            self._binary = binary_path
        else:
            self._binary = (
                shutil.which("espeak-ng")
                or shutil.which("espeak")
                or _autodetect_espeak_binary()
            )

    def is_available(self) -> bool:
        return self._binary is not None

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        if not self.is_available():
            raise RuntimeError(
                "espeak-ng não foi encontrado. Se acabou de instalar, feche e "
                "reabra o IAVOX (o PATH só atualiza em janelas novas). Se "
                "persistir, informe o caminho do espeak-ng.exe em "
                "Configurações avançadas."
            )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self._binary,
                "-v", self.voice,
                "-s", str(self.speed_wpm),
                "-w", str(output_path),
                text,
            ],
            check=True,
            capture_output=True,
        )
        return output_path

    def speak(self, text: str) -> None:
        if not self.is_available():
            raise RuntimeError("espeak-ng não está instalado neste sistema.")
        subprocess.run(
            [self._binary, "-v", self.voice, "-s", str(self.speed_wpm), text],
            check=True,
        )
