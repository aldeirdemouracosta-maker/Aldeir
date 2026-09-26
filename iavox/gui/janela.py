"""
Janela principal do IAVOX — Inteligência Acessível Offline.

Tela inicial com os módulos F1 a F5, barra de navegação (Início, Atividade,
Ajuda, Ajustes) e barra de status com o que está disponível na máquina
(DOSVOX, microfone, OCR, modelos locais).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QShortcut,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iavox_pdf_audio.suite.ambiente import checar_tudo  # noqa: E402

from . import theme  # noqa: E402
from .ajustes import DialogoAjustes  # noqa: E402
from .componentes import ESTADOS_ROBO, Falador, Robo, Tarefa  # noqa: E402
from .contexto import Config, Contexto  # noqa: E402
from .icones import icone, pixmap  # noqa: E402
from .pagina_inicio import PaginaInicio  # noqa: E402
from .paginas import (  # noqa: E402
    PaginaAjuda,
    PaginaAtividade,
    PaginaCaderno,
    PaginaEstuda,
    PaginaFala,
    PaginaLeitor,
    PaginaOlha,
)

TITULO = "IAVOX"
ATALHOS_MODULOS = {"F1": "leitor", "F2": "fala", "F3": "olha", "F4": "estuda", "F5": "atividade"}
ICONES_STATUS = {"DOSVOX": "onda", "Microfone": "microfone", "OCR": "ocr", "Modelos locais": "cubo"}


class JanelaIAVOX(QMainWindow):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.setWindowTitle(TITULO)
        self.setWindowIcon(icone("onda", 64))
        self.resize(1440, 1000)
        self.setMinimumSize(1100, 760)
        self.setStyleSheet(theme.STYLESHEET)

        self.config = config or Config.carregar()
        falador = Falador(self.config.feedback_sonoro, self.config.espeak_binary_path or None)
        self.ctx = Contexto(self.config, falador)
        self.ctx.definir_estado = self.definir_estado
        self.ctx.navegar = self.navegar
        self.ctx.anunciar = self.anunciar
        self.ctx.caderno_mudou = self._caderno_mudou
        self.ctx.perguntas = None
        self._ultima_fala = ""
        self._tarefa_status: Tarefa | None = None

        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        lay = QVBoxLayout(raiz)
        lay.setContentsMargins(0, 0, 0, 18)
        lay.setSpacing(12)

        self.robo_inicio = Robo(300, com_texto=False, retrato=True)
        self.robo_inicio.estado_mudou.connect(self._anunciar_estado)
        self.inicio = PaginaInicio(self.robo_inicio)
        self.inicio.abrir.connect(self.navegar)

        self.paginas = {
            "inicio": self.inicio,
            "leitor": PaginaLeitor(self.ctx),
            "fala": PaginaFala(self.ctx),
            "olha": PaginaOlha(self.ctx),
            "estuda": PaginaEstuda(self.ctx),
            "atividade": PaginaAtividade(self.ctx),
            "caderno": PaginaCaderno(self.ctx),
            "ajuda": PaginaAjuda(self.ctx),
        }
        self.pilha = QStackedWidget()
        for p in self.paginas.values():
            self.pilha.addWidget(p)

        lay.addWidget(self.pilha, 1)
        lay.addWidget(self._barra_nav())
        lay.addWidget(self._barra_status())

        self._atalhos()
        self.navegar("inicio", anunciar=False)
        self.atualizar_status()
        self.anunciar("IAVOX pronto. Use F1 a F5 para escolher um módulo, ou Tab para navegar.")

    # ------------------------------------------------------------ barras

    def _barra_nav(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraNav")
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(10, 8, 10, 8)
        self.grupo_nav = QButtonGroup(self)
        self.grupo_nav.setExclusive(True)
        self.botoes_nav = {}
        for chave, texto, ico in (
            ("inicio", "Início", "casa"),
            ("caderno", "Atividade", "atividade"),
            ("ajuda", "Ajuda", "ajuda"),
            ("ajustes", "Ajustes", "engrenagem"),
        ):
            b = QPushButton(f"   {texto}")
            b.setObjectName("botaoNav")
            b.setIcon(icone(ico, 40, theme.AZUL_ELETRICO if chave == "inicio" else theme.BRANCO))
            b.setIconSize(pixmap(ico, 36).size())
            b.setCheckable(chave != "ajustes")
            b.setAccessibleName("Atividade: Mini Caderno" if chave == "caderno" else texto)
            b.clicked.connect(lambda _=False, c=chave: self._nav_clicado(c))
            if b.isCheckable():
                self.grupo_nav.addButton(b)
            self.botoes_nav[chave] = b
            lay.addWidget(b, 1)
        envolto = QWidget()
        el = QHBoxLayout(envolto)
        el.setContentsMargins(110, 0, 110, 0)
        el.addWidget(barra)
        return envolto

    def _barra_status(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraStatus")
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(24, 6, 24, 6)
        offline = QLabel(f"<span style='color:{theme.AZUL_ELETRICO}; font-size:22px'>●</span>"
                         f"&nbsp;&nbsp;<span style='color:{theme.AZUL_ELETRICO}; font-weight:700; "
                         "letter-spacing:1px'>OFFLINE</span>")
        offline.setAccessibleName("Modo offline")
        lay.addWidget(offline)
        self.itens_status = {}
        for nome, ico in ICONES_STATUS.items():
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet(f"color:{theme.BORDA};")
            lay.addStretch(1)
            lay.addWidget(sep)
            lay.addStretch(1)
            b = QPushButton()
            b.setObjectName("itemStatus")
            b.setAccessibleName(f"{nome}: verificando")
            _pintar_bolinha(b, nome.upper(), theme.TEXTO_SUAVE, ico)
            b.clicked.connect(lambda _=False, n=nome: self._falar_status(n))
            self.itens_status[nome] = b
            lay.addWidget(b)
        self._status = {}
        envolto = QWidget()
        el = QHBoxLayout(envolto)
        el.setContentsMargins(30, 0, 30, 0)
        el.addWidget(barra)
        return envolto

    def atualizar_status(self) -> None:
        self._tarefa_status = Tarefa(checar_tudo, self.config.tesseract_cmd)
        self._tarefa_status.concluida.connect(self._status_pronto)
        self._tarefa_status.start()

    def _status_pronto(self, lista) -> None:
        for st in lista:
            b = self.itens_status.get(st.nome)
            if not b:
                continue
            self._status[st.nome] = st
            b.setToolTip(st.detalhe)
            b.setAccessibleName(st.fala)
            _pintar_bolinha(b, st.nome.upper(), theme.VERDE_OK if st.ok else theme.VERMELHO_ALERTA)

    def _falar_status(self, nome: str) -> None:
        st = self._status.get(nome)
        self.anunciar(st.fala if st else f"{nome}: verificando.")
        self.atualizar_status()

    # ------------------------------------------------------------ navegação

    def _nav_clicado(self, chave: str) -> None:
        if chave == "ajustes":
            self.abrir_ajustes()
        else:
            self.navegar(chave)

    def navegar(self, nome: str, anunciar: bool = True) -> None:
        pagina = self.paginas.get(nome)
        if pagina is None:
            return
        self.pilha.setCurrentWidget(pagina)
        botao = self.botoes_nav.get(nome)
        if botao:
            botao.setChecked(True)
        else:
            self.grupo_nav.setExclusive(False)
            for b in self.grupo_nav.buttons():
                b.setChecked(False)
            self.grupo_nav.setExclusive(True)
        if nome == "inicio":
            self.definir_estado("pronto")
            self.inicio.focar_primeiro()
            if anunciar:
                self.anunciar("Início. F1 a F5 escolhem o módulo.")
        else:
            pagina.ao_entrar()
            if anunciar:
                titulo = {"caderno": "Mini Caderno", "ajuda": "Ajuda"}.get(nome, getattr(pagina, "nome_modulo", nome))
                self.anunciar(f"{titulo} aberto.")

    def abrir_ajustes(self) -> None:
        dlg = DialogoAjustes(self.config, self)
        dlg.setStyleSheet(theme.STYLESHEET)
        if dlg.exec_():
            self.ctx.falador.ativo = self.config.feedback_sonoro
            self.ctx.falador.configurar_binario(self.config.espeak_binary_path)
            self.atualizar_status()
            self.anunciar("Ajustes salvos.")

    def _atalhos(self) -> None:
        for tecla, pagina in ATALHOS_MODULOS.items():
            QShortcut(QKeySequence(tecla), self, activated=lambda p=pagina: self.navegar(p))
        QShortcut(QKeySequence("Esc"), self, activated=self._esc)
        QShortcut(QKeySequence("Ctrl+Shift+M"), self, activated=self._falar_por_voz)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.ctx.falador.falar(self._ultima_fala))
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.ctx.falador.calar)

    def _esc(self) -> None:
        self.ctx.falador.calar()
        atual = self.pilha.currentWidget()
        if hasattr(atual, "cancelar") and atual.cancelar():
            return
        if atual is not self.inicio:
            self.navegar("inicio")

    def _falar_por_voz(self) -> None:
        atual = self.pilha.currentWidget()
        if atual is self.inicio or not hasattr(atual, "falar_por_voz"):
            self.navegar("fala")
            self.paginas["fala"].falar_por_voz()
        else:
            atual.falar_por_voz()

    # ------------------------------------------------------------ robô e voz

    def definir_estado(self, estado: str) -> None:
        self.robo_inicio.definir_estado(estado)
        for p in self.paginas.values():
            robo = getattr(p, "robo", None)
            if robo is not None and robo is not self.robo_inicio:
                robo.definir_estado(estado)

    def _anunciar_estado(self, nome: str, desc: str) -> None:
        if self.robo_inicio.estado == "pronto":
            from .pagina_inicio import SAUDACAO
            self.inicio.balao.definir(SAUDACAO)
        else:
            cor = ESTADOS_ROBO[self.robo_inicio.estado][2]
            self.inicio.balao.definir(f"<span style='color:{cor}; font-size:20px'><b>{nome}</b></span><br>{desc}")

    def anunciar(self, texto: str) -> None:
        """Feedback sonoro (espeak) e descrição acessível para leitores de tela."""
        self._ultima_fala = texto
        self.setAccessibleDescription(texto)
        self.ctx.falador.falar(texto)

    def _caderno_mudou(self) -> None:
        self.paginas["caderno"].atualizar()

    def closeEvent(self, event):  # noqa: N802
        self.ctx.falador.calar()
        super().closeEvent(event)


def _pintar_bolinha(botao: QPushButton, texto: str, cor: str, ico: str = "") -> None:
    """Item de status: ícone + nome + bolinha colorida (verde = ok, vermelho = indisponível)."""
    lbl = botao.findChild(QLabel, "rotuloStatus")
    if lbl is None:
        botao.setText("")
        lay = QHBoxLayout(botao)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(12)
        if ico:
            img = QLabel()
            img.setPixmap(pixmap(ico, 26, theme.BRANCO))
            lay.addWidget(img)
        lbl = QLabel(texto)
        lbl.setObjectName("rotuloStatus")
        lbl.setStyleSheet("font-size:14px; font-weight:600; letter-spacing:1px;")
        lay.addWidget(lbl)
        bolinha = QLabel()
        bolinha.setObjectName("bolinhaStatus")
        bolinha.setFixedSize(14, 14)
        lay.addWidget(bolinha)
        for w in (lbl, bolinha) + ((img,) if ico else ()):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lbl.ensurePolished()
        botao.setMinimumWidth(lbl.sizeHint().width() + (100 if ico else 60))
        botao.setMinimumHeight(40)
    botao.findChild(QLabel, "bolinhaStatus").setStyleSheet(f"background:{cor}; border-radius:7px;")


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("IAVOX")
    janela = JanelaIAVOX()
    janela.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
