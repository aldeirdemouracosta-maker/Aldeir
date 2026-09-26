"""
Diálogo de Configurações Avançadas do IAVOX GUI.

No Linux, essas ferramentas (tesseract, poppler, espeak-ng) normalmente já
ficam no PATH depois do `apt-get install`, então nada precisa ser preenchido
aqui. No Windows, o IAVOX tenta detectar automaticamente o Tesseract no
caminho padrão de instalação — mas se a detecção falhar, ou se o Poppler/
Piper não estiverem no PATH do Windows, este diálogo permite apontar os
caminhos manualmente.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Guarda 3 caminhos opcionais: tesseract_cmd, poppler_path, piper_model_path."""

    def __init__(
        self, parent=None, tesseract_cmd="", poppler_path="", piper_model_path="",
        kokoro_model_path="", kokoro_voices_path="", espeak_binary_path="",
    ):
        super().__init__(parent)
        self.setWindowTitle("Configurações avançadas")
        self.resize(520, 220)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Só preencha se o IAVOX não encontrar essas ferramentas automaticamente "
            "(mais comum no Windows). Deixe em branco para usar a detecção automática."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.tesseract_field = self._path_row(tesseract_cmd, is_file=True)
        form.addRow("Tesseract (tesseract.exe):", self.tesseract_field["container"])

        self.espeak_field = self._path_row(espeak_binary_path, is_file=True)
        form.addRow("espeak-ng (espeak-ng.exe):", self.espeak_field["container"])

        self.poppler_field = self._path_row(poppler_path, is_file=False)
        form.addRow("Pasta bin do Poppler:", self.poppler_field["container"])

        self.piper_field = self._path_row(piper_model_path, is_file=True)
        form.addRow("Modelo de voz Piper (.onnx):", self.piper_field["container"])

        self.kokoro_model_field = self._path_row(kokoro_model_path, is_file=True)
        form.addRow("Modelo Kokoro (kokoro-v1.0*.onnx):", self.kokoro_model_field["container"])

        self.kokoro_voices_field = self._path_row(kokoro_voices_path, is_file=True)
        form.addRow("Vozes Kokoro (voices-v1.0.bin):", self.kokoro_voices_field["container"])

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _path_row(self, initial: str, is_file: bool) -> dict:
        from PyQt5.QtWidgets import QWidget

        row = QHBoxLayout()
        field = QLineEdit(initial)
        browse_btn = QPushButton("Procurar...")

        def browse():
            if is_file:
                path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo")
            else:
                path = QFileDialog.getExistingDirectory(self, "Selecionar pasta")
            if path:
                field.setText(path)

        browse_btn.clicked.connect(browse)
        row.addWidget(field)
        row.addWidget(browse_btn)

        widget = QWidget()
        widget.setLayout(row)
        return {"field": field, "container": widget}

    def values(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.tesseract_field["field"].text().strip(),
            self.poppler_field["field"].text().strip(),
            self.piper_field["field"].text().strip(),
            self.kokoro_model_field["field"].text().strip(),
            self.kokoro_voices_field["field"].text().strip(),
            self.espeak_field["field"].text().strip(),
        )
