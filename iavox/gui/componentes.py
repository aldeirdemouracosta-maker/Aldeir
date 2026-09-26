"""Componentes visuais reutilizáveis da interface IAVOX."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from PyQt5.QtCore import QRectF, QSize, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme
from .icones import pixmap

ASSETS = Path(__file__).resolve().parent / "assets"


# ---------------------------------------------------------------- tarefas

class Tarefa(QThread):
    """Roda uma função em segundo plano; a interface nunca trava (essencial com leitor de tela)."""

    concluida = pyqtSignal(object)
    falhou = pyqtSignal(str)

    def __init__(self, funcao, *args, **kwargs):
        super().__init__()
        self._funcao, self._args, self._kwargs = funcao, args, kwargs

    def run(self) -> None:
        try:
            self.concluida.emit(self._funcao(*self._args, **self._kwargs))
        except Exception as exc:  # noqa: BLE001
            self.falhou.emit(str(exc) or exc.__class__.__name__)


# ---------------------------------------------------------------- voz

class Falador:
    """
    Feedback sonoro: fala mensagens curtas com o espeak-ng, sem travar a
    tela. Uma fala nova interrompe a anterior (como um leitor de tela).
    """

    def __init__(self, ativo: bool = True, binario: str | None = None):
        from iavox_pdf_audio.tts.espeak_engine import EspeakEngine

        self.ativo = ativo
        self._engine = EspeakEngine(binary_path=binario)
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def disponivel(self) -> bool:
        return self._engine.is_available()

    def configurar_binario(self, binario: str | None) -> None:
        from iavox_pdf_audio.tts.espeak_engine import EspeakEngine

        self._engine = EspeakEngine(binary_path=binario or None)

    def calar(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            self._proc = None

    def falar(self, texto: str) -> None:
        if not (self.ativo and texto and self.disponivel):
            return
        self.calar()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with self._lock:
            try:
                self._proc = subprocess.Popen(
                    [self._engine._binary, "-v", self._engine.voice, "-s", str(self._engine.speed_wpm), texto],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
                )
            except OSError:
                self._proc = None


# ---------------------------------------------------------------- cartões

class CartaoModulo(QFrame):
    """Cartão F1..F5: focável pelo teclado, ativa com Enter/Espaço ou clique."""

    ativado = pyqtSignal()

    def __init__(self, tecla: str, nome: str, descricao: str, icone_nome: str, destaque: bool = False):
        super().__init__()
        self.setObjectName("cartaoDestaque" if destaque else "cartao")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{tecla} {nome}")
        self.setAccessibleDescription(descricao.replace("\n", " "))
        self.setToolTip(f"{tecla} — {nome}: {descricao.replace(chr(10), ' ')}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        cor = theme.AMARELO_FOCO if destaque else theme.AZUL_ELETRICO
        icone = QLabel()
        icone.setStyleSheet("background: transparent; border: none;")

        titulo = QHBoxLayout()
        titulo.setSpacing(14)
        lbl_tecla = QLabel(tecla)
        lbl_tecla.setObjectName("teclaDestaque" if destaque else "tecla")
        lbl_nome = QLabel(nome)
        lbl_nome.setObjectName("nomeCartao")
        titulo.addWidget(lbl_tecla)
        titulo.addWidget(lbl_nome)
        titulo.addStretch(1)
        lbl_desc = QLabel(descricao)
        lbl_desc.setObjectName("descCartao")
        lbl_desc.setWordWrap(True)
        for w in (lbl_tecla, lbl_nome, lbl_desc):
            w.setStyleSheet("background: transparent; border: none;")

        if destaque:
            icone.setPixmap(_icone_circular(icone_nome, 118, cor))
            texto = QVBoxLayout()
            texto.setSpacing(8)
            texto.addStretch(1)
            texto.addLayout(titulo)
            texto.addWidget(lbl_desc)
            texto.addStretch(1)
            seta = QLabel()
            seta.setPixmap(pixmap("seta", 62, cor))
            seta.setStyleSheet("background: transparent; border: none;")
            lay = QHBoxLayout(self)
            lay.setContentsMargins(24, 16, 24, 16)
            lay.setSpacing(26)
            lay.addWidget(icone)
            lay.addLayout(texto, 1)
            lay.addWidget(seta)
        else:
            icone.setPixmap(pixmap(icone_nome, 78, cor))
            lay = QVBoxLayout(self)
            lay.setContentsMargins(30, 24, 24, 20)
            lay.setSpacing(10)
            lay.addWidget(icone)
            lay.addStretch(1)
            lay.addLayout(titulo)
            lay.addWidget(lbl_desc)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.ativado.emit()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.ativado.emit()
        super().mouseReleaseEvent(event)


def _icone_circular(nome: str, tamanho: int, cor: str) -> QPixmap:
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(theme.CIANO), 3))
    p.setBrush(QColor("#0E2240"))
    p.drawEllipse(QRectF(4, 4, tamanho - 8, tamanho - 8))
    p.setPen(QPen(QColor(theme.AZUL_ELETRICO), 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(16, 16, tamanho - 32, tamanho - 32))
    interno = pixmap(nome, int(tamanho * 0.5), cor)
    p.drawPixmap(int(tamanho * 0.25), int(tamanho * 0.23), interno)
    p.end()
    return pm


# ---------------------------------------------------------------- robô

ESTADOS_ROBO = {
    # estado: (nome, descrição, cor)
    "pronto": ("Pronto", "Aguardando comando", theme.AZUL_ELETRICO),
    "ouvindo": ("Ouvindo", "Captando sua voz", theme.CIANO),
    "processando": ("Processando", "Analisando informação", theme.AMARELO_FOCO),
    "confirmando": ("Confirmando", "Resposta gerada", theme.VERDE_OK),
    "erro": ("Erro", "Algo deu errado", theme.VERMELHO_ALERTA),
}


class Robo(QWidget):
    """
    Robô do IAVOX com anel colorido indicando o estado. O estado também é
    escrito em texto e exposto ao leitor de tela — nunca depende só da imagem.
    """

    estado_mudou = pyqtSignal(str, str)  # nome, descrição

    def __init__(self, tamanho: int = 150, com_texto: bool = True, retrato: bool = False):
        super().__init__()
        self._tamanho = tamanho
        self._foto = QPixmap(str(ASSETS / "robo.png"))
        self.estado = "pronto"
        self._com_texto = com_texto
        self._retrato = retrato
        if retrato:
            self.setFixedSize(QSize(int(tamanho * 0.87), tamanho))
        else:
            self.setFixedSize(QSize(tamanho + (230 if com_texto else 0), tamanho))
        self._atualizar_acessibilidade()

    def definir_estado(self, estado: str) -> None:
        if estado not in ESTADOS_ROBO:
            estado = "pronto"
        self.estado = estado
        self._atualizar_acessibilidade()
        self.update()
        nome, desc, _ = ESTADOS_ROBO[estado]
        self.estado_mudou.emit(nome, desc)

    def _atualizar_acessibilidade(self) -> None:
        nome, desc, _ = ESTADOS_ROBO[self.estado]
        self.setAccessibleName(f"Estado do IAVOX: {nome}")
        self.setAccessibleDescription(desc)
        self.setToolTip(f"{nome} — {desc}")

    def _pintar_retrato(self, p: QPainter, nome: str, cor: str) -> None:
        """Robô grande da tela inicial, com a etiqueta do estado embaixo."""
        if not self._foto.isNull():
            foto = self._foto.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int((self.width() - foto.width()) / 2), 0, foto)
        f = p.font()
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        largura = p.fontMetrics().horizontalAdvance(nome) + 56
        caixa = QRectF((self.width() - largura) / 2, self.height() - 44, largura, 36)
        p.setPen(QPen(QColor(cor), 2))
        p.setBrush(QColor(theme.AZUL_PROFUNDO))
        p.drawRoundedRect(caixa, 18, 18)
        p.setBrush(QColor(cor))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(caixa.left() + 16, caixa.center().y() - 6, 12, 12))
        p.setPen(QColor(cor))
        p.drawText(caixa.adjusted(34, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, nome)

    def paintEvent(self, _event):  # noqa: N802
        nome, desc, cor = ESTADOS_ROBO[self.estado]
        t = self._tamanho
        if self._retrato:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            self._pintar_retrato(p, nome, cor)
            p.end()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        caminho = QPainterPath()
        caminho.addEllipse(QRectF(6, 6, t - 12, t - 12))
        p.setClipPath(caminho)
        if not self._foto.isNull():
            foto = self._foto.scaled(t, t, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(int((t - foto.width()) / 2), 0, foto)
        p.setClipping(False)
        p.setPen(QPen(QColor(cor), 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(4, 4, t - 8, t - 8))
        if self._com_texto:
            p.setPen(QColor(cor))
            f = p.font()
            f.setPointSize(16)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(t + 16, t / 2 - 30, 214, 30), Qt.AlignLeft | Qt.AlignBottom, nome)
            p.setPen(QColor(theme.TEXTO_SUAVE))
            f.setPointSize(11)
            f.setBold(False)
            p.setFont(f)
            p.drawText(QRectF(t + 16, t / 2 + 2, 214, 26), Qt.AlignLeft | Qt.AlignTop, desc)
        p.end()


class Balao(QFrame):
    """Balão de fala do robô (texto rico, com destaques em azul)."""

    def __init__(self, html: str):
        super().__init__()
        self.setObjectName("balao")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 18, 26, 18)
        self.texto = QLabel(html)
        self.texto.setObjectName("balaoTexto")
        self.texto.setWordWrap(True)
        self.texto.setTextFormat(Qt.RichText)
        self.texto.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.texto)

    def definir(self, html: str) -> None:
        self.texto.setText(html)
