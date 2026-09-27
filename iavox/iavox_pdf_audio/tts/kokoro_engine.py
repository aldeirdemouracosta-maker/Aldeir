"""
Motor de TTS Kokoro (via kokoro-onnx), a 5ª opção do IAVOX.

Kokoro é um modelo de voz neural leve (82M parâmetros, ~80-300MB conforme
a versão) com qualidade bem superior ao espeak-ng, rodando 100% local via
ONNX Runtime — sem PyTorch, sem nuvem. Tem voz nativa em português
brasileiro (vozes pf_dora, pm_alex, pm_santa).

Requer 2 arquivos de modelo baixados manualmente (não incluídos no IAVOX
por serem grandes) e colocados em ~/.iavox/kokoro/, ou apontados via
model_path/voices_path:

  kokoro-v1.0.onnx (ou kokoro-v1.0.int8.onnx, versão leve ~88MB)
  voices-v1.0.bin

Download: https://github.com/thewh1teagle/kokoro-onnx/releases
"""
from __future__ import annotations

from pathlib import Path

from .base import TTSEngine

DEFAULT_VOICE = "pf_dora"  # voz feminina em português brasileiro
DEFAULT_LANG = "pt-br"

MODEL_FILENAMES = ("kokoro-v1.0.onnx", "kokoro-v1.0.int8.onnx", "kokoro-v1.0.fp16.onnx")
VOICES_FILENAME = "voices-v1.0.bin"


class KokoroEngine(TTSEngine):
    name = "Kokoro (voz neural leve, PT-BR)"

    def __init__(
        self,
        model_path: str | Path | None = None,
        voices_path: str | Path | None = None,
        voice: str = DEFAULT_VOICE,
        lang: str = DEFAULT_LANG,
        speed: float = 1.0,
    ):
        self.model_path = Path(model_path) if model_path else self._find_default_model()
        self.voices_path = Path(voices_path) if voices_path else self._find_default_voices()
        self.voice = voice
        self.lang = lang
        self.speed = speed
        self._kokoro = None
        self._import_error: Exception | None = None
        self._try_import()

    def _try_import(self) -> None:
        try:
            from kokoro_onnx import Kokoro  # noqa: N811
            self._Kokoro_cls = Kokoro
        except Exception as exc:  # noqa: BLE001
            self._Kokoro_cls = None
            self._import_error = exc

    @staticmethod
    def _default_dir() -> Path:
        return Path.home() / ".iavox" / "kokoro"

    @classmethod
    def _find_default_model(cls) -> Path | None:
        directory = cls._default_dir()
        for filename in MODEL_FILENAMES:
            candidate = directory / filename
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def _find_default_voices(cls) -> Path | None:
        candidate = cls._default_dir() / VOICES_FILENAME
        return candidate if candidate.exists() else None

    def is_available(self) -> bool:
        return (
            self._Kokoro_cls is not None
            and self.model_path is not None
            and self.model_path.exists()
            and self.voices_path is not None
            and self.voices_path.exists()
        )

    def _ensure_loaded(self):
        if self._kokoro is None:
            if not self.is_available():
                raise RuntimeError(
                    "Kokoro não disponível. Verifique se o pacote está instalado "
                    "(pip install kokoro-onnx) e se os arquivos de modelo "
                    f"({', '.join(MODEL_FILENAMES)} + {VOICES_FILENAME}) estão em "
                    f"{self._default_dir()} — baixe em "
                    "https://github.com/thewh1teagle/kokoro-onnx/releases "
                    f"(detalhe: import={bool(self._Kokoro_cls)}, "
                    f"modelo={self.model_path}, vozes={self.voices_path})"
                )
            self._kokoro = self._Kokoro_cls(str(self.model_path), str(self.voices_path))

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        import soundfile as sf

        self._ensure_loaded()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        samples, sample_rate = self._kokoro.create(
            text, voice=self.voice, speed=self.speed, lang=self.lang
        )
        sf.write(str(output_path), samples, sample_rate)
        return output_path
