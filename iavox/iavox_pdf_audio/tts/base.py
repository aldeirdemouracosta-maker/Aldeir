"""Interface comum para todos os motores de TTS do IAVOX."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSEngine(ABC):
    """Todo motor de voz do IAVOX implementa essa interface."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Retorna True se este motor pode ser usado no ambiente atual."""

    @abstractmethod
    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        """Sintetiza `text` em áudio e salva em `output_path` (wav ou mp3). Retorna o Path final."""

    def speak(self, text: str) -> None:
        """Fala o texto diretamente (leitura ao vivo), quando o motor suportar."""
        raise NotImplementedError(f"{self.name} não suporta leitura ao vivo direta.")
