"""Tela inicial do IAVOX — cartões F1 a F5, robô, balão e dicas rápidas."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .componentes import Balao, CartaoModulo, Robo
from .icones import pixmap

MODULOS = [
    # tecla, nome da página, nome, descrição, ícone
    ("F1", "leitor", "LeitorVox", "Ler imagem, PDF\nou tela", "documento"),
    ("F2", "fala", "FalaVox", "Responder\ncom voz", "fala"),
    ("F3", "olha", "OlhaVox", "Descrever\nimagens", "olho"),
    ("F4", "estuda", "EstudaVox", "Resumo e\nperguntas", "livro"),
    ("F5", "atividade", "Modo Atividade", "Ouvir, responder, confirmar\ne continuar", "estrela"),
]

SAUDACAO = (
    f"Olá! Eu sou o <span style='color:{theme.AZUL_ELETRICO}'>IAVOX</span>.<br><br>"
    f"Estou aqui para ajudar você<br>com <span style='color:{theme.AZUL_ELETRICO}'>inteligência "
    f"e acessibilidade</span>.<br>Tudo funciona <span style='color:{theme.AZUL_ELETRICO}'>100% offline</span>."
)

DICAS = [
    (["Ctrl", "Shift", "M"], "responder com voz"),
    (["Enter"], "confirmar"),
    (["Espaço"], "gravar novamente"),
    (["Esc"], "cancelar / voltar"),
]


def _logo() -> QLabel:
    a = theme.AZUL_ELETRICO
    lbl = QLabel(
        f"<span style='color:{theme.BRANCO}'>I</span><span style='color:{a}'>A</span>"
        f"<span style='color:{theme.BRANCO}'>VOX</span>"
    )
    lbl.setObjectName("logo")
    lbl.setTextFormat(Qt.RichText)
    lbl.setAccessibleName("IAVOX")
    return lbl


class PaginaInicio(QWidget):
    abrir = pyqtSignal(str)

    def __init__(self, robo: Robo):
        super().__init__()
        self.setObjectName("pagina")
        self.cartoes: dict[str, CartaoModulo] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(34, 18, 34, 10)
        raiz.setSpacing(18)

        # ---- cabeçalho: logo + badge + balão + robô
        topo = QHBoxLayout()
        marca = QVBoxLayout()
        marca.setSpacing(2)
        linha_logo = QHBoxLayout()
        linha_logo.addWidget(_logo())
        linha_logo.addSpacing(26)
        badge = QLabel("●  OFFLINE")
        badge.setObjectName("badge")
        badge.setAccessibleName("Modo offline: nenhuma função depende de internet")
        linha_logo.addWidget(badge, 0, Qt.AlignVCenter)
        linha_logo.addStretch(1)
        marca.addLayout(linha_logo)
        slogan = QLabel("Inteligência Acessível Offline")
        slogan.setObjectName("slogan")
        sub = QLabel("Suíte paralela para apoio ao DOSVOX")
        sub.setObjectName("subslogan")
        marca.addWidget(slogan)
        marca.addWidget(sub)
        marca.addStretch(1)
        topo.addLayout(marca, 1)

        self.balao = Balao(SAUDACAO)
        self.balao.setFixedWidth(360)
        topo.addWidget(self.balao, 0, Qt.AlignTop)
        topo.addSpacing(250)
        raiz.addLayout(topo)
        self.robo = robo

        # ---- cartões + dicas
        grade = QGridLayout()
        grade.setHorizontalSpacing(22)
        grade.setVerticalSpacing(22)
        for i, (tecla, pagina, nome, desc, icone) in enumerate(MODULOS):
            cartao = CartaoModulo(tecla, nome, desc, icone, destaque=(tecla == "F5"))
            cartao.ativado.connect(lambda p=pagina: self.abrir.emit(p))
            self.cartoes[pagina] = cartao
            if tecla == "F5":
                grade.addWidget(cartao, 1, 1, 1, 2)
            elif tecla == "F4":
                grade.addWidget(cartao, 1, 0)
            else:
                grade.addWidget(cartao, 0, i)
        grade.addWidget(self.robo, 0, 3, Qt.AlignHCenter | Qt.AlignBottom)
        grade.addWidget(self._dicas(), 1, 3, Qt.AlignBottom)
        for c in range(3):
            grade.setColumnStretch(c, 1)
        grade.setColumnStretch(3, 1)
        raiz.addLayout(grade, 1)

        # ordem de Tab = ordem visual
        ordem = [self.cartoes[p] for p in ("leitor", "fala", "olha", "estuda", "atividade")]
        for a, b in zip(ordem, ordem[1:]):
            QWidget.setTabOrder(a, b)

    def _dicas(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("painel")
        painel.setAccessibleName("Dicas rápidas de teclado")
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        titulo = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(pixmap("ajuda", 24))
        ico.setStyleSheet("border:none; background:transparent;")
        lbl = QLabel("DICAS RÁPIDAS")
        lbl.setObjectName("rotuloSecao")
        lbl.setStyleSheet("border:none; background:transparent; font-size:15px;")
        titulo.addWidget(ico)
        titulo.addWidget(lbl)
        titulo.addStretch(1)
        lay.addLayout(titulo)
        for teclas, acao in DICAS:
            linha = QHBoxLayout()
            linha.setSpacing(6)
            for j, t in enumerate(teclas):
                if j:
                    mais = QLabel("+")
                    mais.setStyleSheet("border:none; background:transparent;")
                    linha.addWidget(mais)
                k = QLabel(t)
                k.setObjectName("teclaAtalho")
                linha.addWidget(k)
            linha.addStretch(1)
            desc = QLabel(f"=  {acao}")
            desc.setStyleSheet("border:none; background:transparent; font-size:14px;")
            linha.addWidget(desc)
            lay.addLayout(linha)
        return painel

    def focar_primeiro(self) -> None:
        self.cartoes["leitor"].setFocus()
