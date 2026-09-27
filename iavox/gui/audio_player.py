"""
Player de áudio do IAVOX GUI.

Tenta usar QtMultimedia (toca dentro do próprio app, com botão de play/pause).
Se não estiver disponível no sistema (bibliotecas de áudio ausentes), cai
graciosamente para abrir o arquivo no tocador padrão do sistema operacional
(Linux: xdg-open; Windows: os.startfile; macOS: open) — sempre funciona.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger("iavox.gui.player")


class AudioPlayer:
    """
    Uso:
        player = AudioPlayer()
        player.play(caminho_wav)

    Se `has_inline_playback` for True, o chamador pode usar player.qt_player
    (QMediaPlayer) diretamente para integrar play/pause na UI. Caso
    contrário, `play()` já abre no tocador do sistema.
    """

    def __init__(self):
        self.qt_player = None
        self.has_inline_playback = self._try_setup_qt_player()

    def _try_setup_qt_player(self) -> bool:
        try:
            from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer  # noqa: F401
            self.qt_player = QMediaPlayer()
            self._QMediaContent = QMediaContent
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("Playback inline (QtMultimedia) indisponível: %s", exc)
            return False

    def play(self, wav_path: str | Path) -> None:
        wav_path = Path(wav_path)
        if not wav_path.exists():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {wav_path}")

        if self.has_inline_playback:
            from PyQt5.QtCore import QUrl
            self.qt_player.setMedia(self._QMediaContent(QUrl.fromLocalFile(str(wav_path))))
            self.qt_player.play()
            return

        self._play_with_system_default(wav_path)

    def pause(self) -> None:
        if self.has_inline_playback and self.qt_player:
            self.qt_player.pause()

    def stop(self) -> None:
        if self.has_inline_playback and self.qt_player:
            self.qt_player.stop()

    @staticmethod
    def _play_with_system_default(wav_path: Path) -> None:
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(str(wav_path))  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", str(wav_path)])
            else:  # Linux e afins
                subprocess.Popen(["xdg-open", str(wav_path)])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Não foi possível abrir o tocador padrão: %s", exc)
            raise RuntimeError(
                f"Não foi possível reproduzir automaticamente. Abra manualmente: {wav_path}"
            ) from exc
