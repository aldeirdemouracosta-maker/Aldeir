"""
IAVOX - Leitor de PDF em Áudio (interface desktop)
=====================================================
Layout inspirado no mockup enviado por Aldeir: barra lateral com histórico de
documentos, cartão central com o documento carregado, opções de leitura, e
um botão de ação principal em formato de círculo (▶ Ouvir / Gerar áudio).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iavox_pdf_audio.core.reader import ReadingOptions
from iavox_pdf_audio.tts.selector import ENGINE_CHOICES

from .audio_player import AudioPlayer
from .settings_dialog import SettingsDialog
from .styles import STYLESHEET
from .worker import ReaderWorker

APP_TITLE = "IAVOX — Leitor de PDF em Áudio"

TTS_LABELS = {
    "automatico": "Automático (melhor disponível)",
    "offline": "Offline básico (espeak-ng)",
    "piper": "Offline natural (Piper)",
    "kokoro": "Kokoro (voz neural leve, PT-BR)",
    "ia": "Voz por IA (Coqui TTS)",
}
MODE_LABELS = {"completo": "Texto completo", "resumo": "Resumo por IA"}
DENSITY_LABELS = {"curto": "Curto", "medio": "Médio", "detalhado": "Detalhado"}


def make_card() -> QFrame:
    card = QFrame()
    card.setProperty("class", "card")
    card.setFrameShape(QFrame.NoFrame)
    return card


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 640)
        self.setStyleSheet(STYLESHEET)

        self.current_pdf: str | None = None
        self.current_audio: str | None = None
        self.worker: ReaderWorker | None = None
        self.player = AudioPlayer()
        # Caminhos manuais opcionais (Windows), definidos via diálogo de Configurações.
        self.tesseract_cmd = ""
        self.poppler_path = ""
        self.piper_model_path = ""
        self.kokoro_model_path = ""
        self.kokoro_voices_path = ""
        self.espeak_binary_path = ""

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar(), 0)
        root.addWidget(self._build_main_panel(), 1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand_bar = QWidget()
        brand_bar.setObjectName("brandBar")
        brand_layout = QHBoxLayout(brand_bar)
        brand_title = QLabel("📖 IAVOX")
        brand_title.setObjectName("brandTitle")
        brand_layout.addWidget(brand_title)
        layout.addWidget(brand_bar)

        section = QLabel("DOCUMENTOS RECENTES")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.itemDoubleClicked.connect(self._open_from_history)
        layout.addWidget(self.history_list, 1)

        open_btn = QPushButton("＋  Abrir novo PDF")
        open_btn.clicked.connect(self._choose_pdf)
        open_btn.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(open_btn)

        settings_btn = QPushButton("⚙  Configurações avançadas")
        settings_btn.setObjectName("secondaryPill")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        layout.setContentsMargins(0, 0, 0, 12)

        return sidebar

    def _build_main_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading = QLabel("Leitor de PDF em Áudio")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        subtitle = QLabel("Escolha um PDF, ajuste as opções de leitura e ouça — tudo local, sem nuvem.")
        subtitle.setObjectName("docSubtitle")
        layout.addWidget(subtitle)

        layout.addWidget(self._build_doc_card())
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_action_row())
        layout.addWidget(self._build_status_card(), 1)

        return panel

    def _build_doc_card(self) -> QFrame:
        card = make_card()
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 16, 18, 16)

        icon = QLabel("📄")
        icon.setStyleSheet("font-size: 28px;")
        row.addWidget(icon)

        text_col = QVBoxLayout()
        self.doc_title = QLabel("Nenhum PDF selecionado")
        self.doc_title.setObjectName("docTitle")
        self.doc_subtitle = QLabel("Clique em “Escolher PDF” para começar")
        self.doc_subtitle.setObjectName("docSubtitle")
        text_col.addWidget(self.doc_title)
        text_col.addWidget(self.doc_subtitle)
        row.addLayout(text_col, 1)

        choose_btn = QPushButton("Escolher PDF")
        choose_btn.setObjectName("secondaryPill")
        choose_btn.clicked.connect(self._choose_pdf)
        row.addWidget(choose_btn)

        return card

    def _build_options_card(self) -> QFrame:
        card = make_card()
        grid = QHBoxLayout(card)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setSpacing(20)

        grid.addLayout(self._labeled(
            "Modo de leitura", self._make_combo(MODE_LABELS, "mode_combo")
        ))
        grid.addLayout(self._labeled(
            "Densidade", self._make_combo(DENSITY_LABELS, "density_combo")
        ))
        grid.addLayout(self._labeled(
            "Motor de voz", self._make_combo(TTS_LABELS, "tts_combo", default="automatico")
        ))

        img_col = QVBoxLayout()
        img_label = QLabel("Imagens")
        img_label.setObjectName("sectionLabel")
        img_col.addWidget(img_label)
        self.describe_images_check = QCheckBox("Descrever imagens (audiodescrição por IA)")
        self.describe_images_check.setChecked(True)
        img_col.addWidget(self.describe_images_check)
        self.save_audio_check = QCheckBox("Salvar como arquivo de áudio")
        self.save_audio_check.setChecked(True)
        img_col.addWidget(self.save_audio_check)
        grid.addLayout(img_col, 1)

        self.mode_combo.currentIndexChanged.connect(self._sync_density_enabled)
        self._sync_density_enabled()

        return card

    def _make_combo(self, labels: dict[str, str], attr_name: str, default: str | None = None) -> QComboBox:
        combo = QComboBox()
        for key, label in labels.items():
            combo.addItem(label, userData=key)
        if default:
            idx = combo.findData(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        setattr(self, attr_name, combo)
        return combo

    @staticmethod
    def _labeled(title: str, widget: QWidget) -> QVBoxLayout:
        col = QVBoxLayout()
        label = QLabel(title.upper())
        label.setObjectName("sectionLabel")
        col.addWidget(label)
        col.addWidget(widget)
        return col

    def _sync_density_enabled(self) -> None:
        is_resumo = self.mode_combo.currentData() == "resumo"
        self.density_combo.setEnabled(is_resumo)

    def _build_action_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)

        self.generate_btn = QPushButton("Gerar leitura")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._start_generation)
        layout.addWidget(self.generate_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("playCircle")
        self.play_btn.setFixedSize(64, 64)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_audio)
        layout.addWidget(self.play_btn)

        layout.addStretch(1)

        self.status_chip = QLabel("Pronto")
        self.status_chip.setObjectName("statusChip")
        layout.addWidget(self.status_chip, 0, Qt.AlignRight)

        return row

    def _build_status_card(self) -> QFrame:
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)

        return card

    # ------------------------------------------------------------- ações

    def _choose_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self._set_current_pdf(path)

    def _set_current_pdf(self, path: str) -> None:
        self.current_pdf = path
        name = Path(path).name
        self.doc_title.setText(name)
        self.doc_subtitle.setText(path)
        self.play_btn.setEnabled(False)
        self.current_audio = None

        existing = self.history_list.findItems(path, Qt.MatchExactly)
        if not existing:
            self.history_list.insertItem(0, path)
            self.history_list.item(0).setText(name)
            self.history_list.item(0).setData(Qt.UserRole, path)

    def _open_from_history(self, item) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self._set_current_pdf(path)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self,
            tesseract_cmd=self.tesseract_cmd,
            poppler_path=self.poppler_path,
            piper_model_path=self.piper_model_path,
            kokoro_model_path=self.kokoro_model_path,
            kokoro_voices_path=self.kokoro_voices_path,
            espeak_binary_path=self.espeak_binary_path,
        )
        if dialog.exec_() == dialog.Accepted:
            (
                self.tesseract_cmd,
                self.poppler_path,
                self.piper_model_path,
                self.kokoro_model_path,
                self.kokoro_voices_path,
                self.espeak_binary_path,
            ) = dialog.values()
            self._on_log("Configurações avançadas atualizadas.")

    def _start_generation(self) -> None:
        if not self.current_pdf:
            QMessageBox.warning(self, APP_TITLE, "Escolha um PDF primeiro.")
            return
        if self.worker and self.worker.isRunning():
            return

        options = ReadingOptions(
            mode=self.mode_combo.currentData(),
            density=self.density_combo.currentData(),
            describe_images=self.describe_images_check.isChecked(),
            tts_choice=self.tts_combo.currentData(),
            save_audio=self.save_audio_check.isChecked(),
            output_dir=str(Path.home() / "IAVOX_audios"),
            piper_model_path=self.piper_model_path or None,
            kokoro_model_path=self.kokoro_model_path or None,
            kokoro_voices_path=self.kokoro_voices_path or None,
            espeak_binary_path=self.espeak_binary_path or None,
        )

        self.log_box.clear()
        self.progress_bar.setRange(0, 0)  # indeterminado até sabermos o total de páginas
        self.generate_btn.setEnabled(False)
        self.status_chip.setText("Processando...")

        self.worker = ReaderWorker(self.current_pdf, options)
        if self.tesseract_cmd or self.poppler_path:
            self.worker.reader.extractor.poppler_path = self.poppler_path or None
            if self.tesseract_cmd:
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
                except ImportError:
                    pass
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished_audio.connect(self._on_audio_ready)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_progress(self, current: int, total: int, stage: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self._on_log(f"Página {current}/{total} — {stage}")

    def _on_log(self, message: str) -> None:
        self.log_box.append(message)

    def _on_audio_ready(self, audio_path: str) -> None:
        self.current_audio = audio_path
        self.play_btn.setEnabled(True)
        self.status_chip.setText("Áudio pronto")

    def _on_failed(self, message: str) -> None:
        self.status_chip.setText("Erro")
        self._on_log(f"ERRO: {message}")
        QMessageBox.critical(self, APP_TITLE, message)

    def _on_worker_finished(self) -> None:
        self.generate_btn.setEnabled(True)
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
        if self.status_chip.text() == "Processando...":
            self.status_chip.setText("Concluído")

    def _play_audio(self) -> None:
        if not self.current_audio:
            return
        try:
            self.player.play(self.current_audio)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_TITLE, str(exc))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
