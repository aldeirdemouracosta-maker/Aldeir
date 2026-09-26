"""
Motor de TTS por IA usando Coqui TTS (modelo neural local, sem nuvem).
Voz mais expressiva/natural que Piper, ao custo de mais RAM/CPU e um
carregamento inicial mais lento do modelo.

Requer o pacote opcional `TTS` (Coqui): pip install TTS
"""
from __future__ import annotations

from pathlib import Path

from .base import TTSEngine

DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


class AITTSEngine(TTSEngine):
    name = "IA (Coqui TTS neural)"

    def __init__(self, model_name: str = DEFAULT_MODEL, speaker_wav: str | None = None):
        self.model_name = model_name
        self.speaker_wav = speaker_wav  # amostra de voz opcional, para clonagem de voz
        self._tts = None
        self._import_error: Exception | None = None
        self._try_import()

    def _try_import(self) -> None:
        try:
            from TTS.api import TTS  # noqa: N811 - nome da lib é TTS mesmo
            self._TTS_cls = TTS
        except Exception as exc:  # noqa: BLE001
            self._TTS_cls = None
            self._import_error = exc

    def is_available(self) -> bool:
        return self._TTS_cls is not None

    def _ensure_loaded(self):
        if self._tts is None:
            if not self.is_available():
                raise RuntimeError(
                    "Coqui TTS não está instalado. Rode: pip install TTS "
                    f"(erro original: {self._import_error})"
                )
            self._tts = self._TTS_cls(self.model_name)

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        self._ensure_loaded()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"text": text, "file_path": str(output_path), "language": "pt"}
        if self.speaker_wav:
            kwargs["speaker_wav"] = self.speaker_wav
        self._tts.tts_to_file(**kwargs)
        return output_path
