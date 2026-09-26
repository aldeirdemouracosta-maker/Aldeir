"""
Motor de TTS offline com Piper (vozes neurais locais, sem nuvem).
Muito mais natural que espeak-ng, mas exige o binário `piper` e um modelo de
voz .onnx baixado previamente (ex: pt_BR-faber-medium.onnx).

Modelos de voz em português: https://github.com/rhasspy/piper/releases
(o download do modelo é feito manualmente pelo usuário, para manter o IAVOX
sem dependências de rede obrigatórias em tempo de execução).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import TTSEngine

DEFAULT_MODEL_ENV_HINT = (
    "Nenhum modelo de voz Piper configurado. Baixe um modelo .onnx em "
    "português (ex: pt_BR-faber-medium.onnx) e informe o caminho com "
    "--piper-model, ou coloque em ~/.iavox/piper_voices/"
)


class PiperEngine(TTSEngine):
    name = "Piper TTS (offline, voz natural)"

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path) if model_path else self._find_default_model()
        self._binary = shutil.which("piper")

    @staticmethod
    def _find_default_model() -> Path | None:
        default_dir = Path.home() / ".iavox" / "piper_voices"
        if default_dir.exists():
            candidates = sorted(default_dir.glob("*.onnx"))
            if candidates:
                return candidates[0]
        return None

    def is_available(self) -> bool:
        return self._binary is not None and self.model_path is not None and self.model_path.exists()

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        if not self.is_available():
            raise RuntimeError(
                f"Piper não disponível (binário: {bool(self._binary)}, "
                f"modelo: {self.model_path}). {DEFAULT_MODEL_ENV_HINT}"
            )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [self._binary, "--model", str(self.model_path), "--output_file", str(output_path)],
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
        )
        return output_path
