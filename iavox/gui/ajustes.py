"""
Ajustes do IAVOX (Configurações avançadas).

No Linux as ferramentas normalmente já estão no PATH. No Windows o IAVOX
tenta detectar sozinho; cada campo mostra "✓ detectado automaticamente"
quando encontra a ferramenta, e só precisa ser preenchido se não encontrar.
"""
from __future__ import annotations

import shutil

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iavox_pdf_audio.core.extractor import _autodetect_tesseract_cmd
from iavox_pdf_audio.tts.espeak_engine import _autodetect_espeak_binary

from . import theme
from .contexto import Config
from .paginas import TTS_LABELS

MODELOS_WHISPER = {
    "tiny": "tiny — mais rápido, menos preciso",
    "base": "base — rápido",
    "small": "small — equilibrado (recomendado)",
    "medium": "medium — mais preciso, mais lento",
}


def _detectado(texto: str | None) -> str:
    if texto:
        return f"<span style='color:{theme.VERDE_OK}'>✓ detectado automaticamente</span>"
    return f"<span style='color:{theme.AMARELO_FOCO}'>não encontrado — informe o caminho</span>"


class DialogoAjustes(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Ajustes — Configurações avançadas")
        self.resize(720, 560)
        lay = QVBoxLayout(self)

        titulo = QLabel("Configurações avançadas")
        titulo.setObjectName("tituloPagina")
        lay.addWidget(titulo)
        sub = QLabel("Windows / Linux — deixe em branco para usar a detecção automática.")
        sub.setObjectName("descricaoPagina")
        lay.addWidget(sub)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        self.feedback = QCheckBox("Falar mensagens de confirmação e alertas (feedback sonoro)")
        self.feedback.setChecked(config.feedback_sonoro)
        form.addRow(self.feedback)

        self.motor = QComboBox()
        for k, v in TTS_LABELS.items():
            self.motor.addItem(v, userData=k)
        self.motor.setCurrentIndex(max(0, self.motor.findData(config.motor_voz)))
        form.addRow("Motor de voz padrão:", self.motor)

        self.whisper = QComboBox()
        for k, v in MODELOS_WHISPER.items():
            self.whisper.addItem(v, userData=k)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(config.modelo_whisper)))
        form.addRow("Modelo do Whisper (FalaVox):", self.whisper)

        tesseract_auto = shutil.which("tesseract") or _autodetect_tesseract_cmd()
        espeak_auto = shutil.which("espeak-ng") or shutil.which("espeak") or _autodetect_espeak_binary()
        poppler_auto = shutil.which("pdftoppm")

        self.campos = {}
        for chave, rotulo, eh_arquivo, auto in (
            ("tesseract_cmd", "Caminho do Tesseract OCR", True, tesseract_auto),
            ("poppler_path", "Caminho do Poppler (pdftoppm)", False, poppler_auto),
            ("espeak_binary_path", "eSpeak NG (espeak-ng.exe)", True, espeak_auto),
            ("piper_model_path", "Modelo de voz Piper (.onnx)", True, None),
            ("kokoro_model_path", "Modelo Kokoro (.onnx)", True, None),
            ("kokoro_voices_path", "Vozes Kokoro (voices-v1.0.bin)", True, None),
        ):
            campo, linha = self._linha_caminho(getattr(config, chave), eh_arquivo, rotulo)
            self.campos[chave] = campo
            if chave in ("tesseract_cmd", "poppler_path", "espeak_binary_path"):
                status = QLabel(_detectado(getattr(config, chave) or auto))
                caixa = QVBoxLayout()
                caixa.setSpacing(2)
                caixa.addWidget(linha)
                caixa.addWidget(status)
                w = QWidget()
                w.setLayout(caixa)
                form.addRow(rotulo + ":", w)
            else:
                form.addRow(rotulo + ":", linha)
        lay.addLayout(form)
        lay.addStretch(1)

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def _linha_caminho(self, inicial: str, eh_arquivo: bool, rotulo: str):
        campo = QLineEdit(inicial)
        campo.setAccessibleName(rotulo)
        procurar = QPushButton("Procurar...")
        procurar.setAccessibleName(f"Procurar {rotulo}")

        def escolher():
            if eh_arquivo:
                caminho, _ = QFileDialog.getOpenFileName(self, rotulo)
            else:
                caminho = QFileDialog.getExistingDirectory(self, rotulo)
            if caminho:
                campo.setText(caminho)

        procurar.clicked.connect(escolher)
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(campo, 1)
        linha.addWidget(procurar)
        w = QWidget()
        w.setLayout(linha)
        return campo, w

    def _salvar(self) -> None:
        c = self.config
        c.feedback_sonoro = self.feedback.isChecked()
        c.motor_voz = self.motor.currentData()
        c.modelo_whisper = self.whisper.currentData()
        for chave, campo in self.campos.items():
            setattr(c, chave, campo.text().strip())
        c.salvar()
        self.accept()
