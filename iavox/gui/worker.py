"""Thread de trabalho: roda extração/resumo/audiodescrição/TTS em background,
para a interface nunca travar (importante para quem usa leitor de tela)."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iavox_pdf_audio.core.reader import IAVOXPDFReader, ReadingOptions, ReadingScript


class ReaderWorker(QThread):
    progress = pyqtSignal(int, int, str)   # atual, total, etapa
    log = pyqtSignal(str)
    finished_script = pyqtSignal(object)   # ReadingScript
    finished_audio = pyqtSignal(str)       # caminho do wav gerado
    failed = pyqtSignal(str)

    def __init__(self, pdf_path: str, options: ReadingOptions, only_build_script: bool = False):
        super().__init__()
        self.pdf_path = pdf_path
        self.options = options
        self.only_build_script = only_build_script
        self.reader = IAVOXPDFReader()

    def run(self) -> None:
        try:
            self.log.emit(f"Lendo {Path(self.pdf_path).name}...")
            script: ReadingScript = self.reader.build_script(
                self.pdf_path, self.options, progress_cb=self._on_progress
            )
            self.log.emit(
                f"Roteiro pronto: {script.pages_count} página(s), "
                f"{script.image_descriptions_count} imagem(ns) descrita(s)"
                + (", OCR usado" if script.used_ocr else "")
            )
            self.finished_script.emit(script)

            if not self.only_build_script and self.options.save_audio:
                self.log.emit(f"Gerando áudio (motor: {self.options.tts_choice})...")
                audio_path = self.reader.synthesize(script, self.options)
                self.log.emit(f"Áudio salvo em {audio_path}")
                self.finished_audio.emit(str(audio_path))

        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _on_progress(self, current: int, total: int, stage: str) -> None:
        self.progress.emit(current, total, stage)
