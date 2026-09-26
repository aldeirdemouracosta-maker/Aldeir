"""Telas dos módulos do IAVOX: LeitorVox, FalaVox, OlhaVox, EstudaVox,
Modo Atividade, Mini Caderno e Ajuda."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QGuiApplication, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iavox_pdf_audio.core.reader import ReadingOptions
from iavox_pdf_audio.suite import voz_entrada
from iavox_pdf_audio.suite.caderno import abrir_no_editor, encontrar_editor_dosvox
from iavox_pdf_audio.suite.estudo import EstudaVox, ler_texto_de_arquivo
from iavox_pdf_audio.suite.olhavox import descrever_imagem, ler_texto_imagem

from . import theme
from .audio_player import AudioPlayer
from .componentes import ESTADOS_ROBO, Robo, Tarefa
from .contexto import Contexto
from .icones import pixmap
from .worker import ReaderWorker

TTS_LABELS = {
    "automatico": "Automático (melhor disponível)",
    "offline": "Offline básico (espeak-ng)",
    "piper": "Offline natural (Piper)",
    "kokoro": "Kokoro (voz neural leve, PT-BR)",
    "ia": "Voz por IA (Coqui TTS)",
}
MODE_LABELS = {"completo": "Leitura completa", "resumo": "Resumo por IA"}
DENSITY_LABELS = {"curto": "Curto", "medio": "Médio", "detalhado": "Detalhado"}
FILTRO_IMAGENS = "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"


def combo(opcoes: dict[str, str], padrao: str | None = None, nome: str = "") -> QComboBox:
    c = QComboBox()
    for chave, rotulo in opcoes.items():
        c.addItem(rotulo, userData=chave)
    if padrao:
        c.setCurrentIndex(max(0, c.findData(padrao)))
    c.setAccessibleName(nome)
    return c


def rotulado(titulo: str, widget: QWidget) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(6)
    lbl = QLabel(titulo.upper())
    lbl.setObjectName("rotuloSecao")
    lbl.setBuddy(widget)
    col.addWidget(lbl)
    col.addWidget(widget)
    return col


def painel() -> QFrame:
    p = QFrame()
    p.setObjectName("painel")
    return p


def caixa_resultado(nome: str) -> QTextEdit:
    caixa = QTextEdit()
    caixa.setReadOnly(True)
    caixa.setAccessibleName(nome)
    caixa.setTextInteractionFlags(Qt.TextSelectableByKeyboard | Qt.TextSelectableByMouse)
    caixa.setPlaceholderText("O resultado aparece aqui e é lido em voz alta.")
    return caixa


# ====================================================================== base

class PaginaModulo(QWidget):
    """Cabeçalho comum: voltar, ícone, título e descrição."""

    nome_modulo = ""

    def __init__(self, ctx: Contexto, titulo: str, descricao: str, icone: str, tecla: str):
        super().__init__()
        self.setObjectName("pagina")
        self.ctx = ctx
        self._tarefas: list[Tarefa] = []

        self.raiz = QVBoxLayout(self)
        self.raiz.setContentsMargins(34, 22, 34, 10)
        self.raiz.setSpacing(16)

        topo = QHBoxLayout()
        topo.setSpacing(16)
        voltar = QPushButton("  Início (Esc)")
        voltar.setObjectName("botaoVoltar")
        voltar.setIcon(_icone_qt("voltar"))
        voltar.setAccessibleName("Voltar para o início")
        voltar.clicked.connect(lambda: ctx.navegar("inicio"))
        topo.addWidget(voltar, 0, Qt.AlignTop)
        ico = QLabel()
        ico.setPixmap(pixmap(icone, 56))
        topo.addWidget(ico)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        t = QLabel(f"<span style='color:{theme.AZUL_ELETRICO}'>{tecla}</span>&nbsp;&nbsp;{titulo}")
        t.setObjectName("tituloPagina")
        t.setTextFormat(Qt.RichText)
        d = QLabel(descricao)
        d.setObjectName("descricaoPagina")
        d.setWordWrap(True)
        textos.addWidget(t)
        textos.addWidget(d)
        topo.addLayout(textos, 1)
        self.robo = Robo(72, com_texto=True)
        topo.addWidget(self.robo, 0, Qt.AlignTop)
        self.raiz.addLayout(topo)

    # tarefas em segundo plano -------------------------------------------
    def rodar(self, funcao, *args, ao_concluir=None, ao_falhar=None, estado="processando", **kwargs) -> Tarefa:
        tarefa = Tarefa(funcao, *args, **kwargs)
        self._tarefas.append(tarefa)
        if estado:
            self.ctx.definir_estado(estado)
        if ao_concluir:
            tarefa.concluida.connect(ao_concluir)
        tarefa.falhou.connect(ao_falhar or self.erro)
        tarefa.finished.connect(lambda: self._tarefas.remove(tarefa) if tarefa in self._tarefas else None)
        tarefa.start()
        return tarefa

    def erro(self, mensagem: str) -> None:
        self.ctx.definir_estado("erro")
        self.ctx.anunciar(f"Erro. {mensagem}")
        QMessageBox.warning(self, "IAVOX", mensagem)

    def resultado(self, caixa: QTextEdit, texto: str, falar: str | None = None) -> None:
        caixa.setPlainText(texto)
        self.ctx.definir_estado("confirmando")
        self.ctx.registrar(self.nome_modulo, texto)
        self.ctx.falador.falar(falar or texto)
        caixa.setFocus()

    # hooks da janela ------------------------------------------------------
    def ao_entrar(self) -> None:
        """Chamado quando a tela é aberta."""

    def cancelar(self) -> bool:
        """Esc: retorna True se a tela consumiu o Esc (ex.: cancelou uma gravação)."""
        return False

    def falar_por_voz(self) -> None:
        """Ctrl+Shift+M dentro desta tela (padrão: abre o FalaVox)."""
        self.ctx.navegar("fala")


def _icone_qt(nome: str):
    from .icones import icone
    return icone(nome, 22, theme.BRANCO)


# ================================================================= F1 Leitor

class PaginaLeitor(PaginaModulo):
    nome_modulo = "LeitorVox"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "LeitorVox", "Ler imagem, PDF ou tela — extração, resumo por IA e audiodescrição de imagens.", "documento", "F1")
        self.pdf_atual: str | None = None
        self.audio_atual: str | None = None
        self.worker: ReaderWorker | None = None
        self.player = AudioPlayer()

        corpo = QHBoxLayout()
        corpo.setSpacing(18)

        # ---- lateral: PDFs recentes (do mockup)
        lateral = painel()
        lateral.setFixedWidth(270)
        lat = QVBoxLayout(lateral)
        lat.setContentsMargins(16, 16, 16, 16)
        rot = QLabel("PDFS RECENTES")
        rot.setObjectName("rotuloSecao")
        lat.addWidget(rot)
        self.recentes = QListWidget()
        self.recentes.setAccessibleName("PDFs recentes")
        self.recentes.itemActivated.connect(lambda it: self._definir_pdf(it.data(Qt.UserRole)))
        lat.addWidget(self.recentes, 1)
        novo = QPushButton("+ Novo PDF")
        novo.clicked.connect(self._escolher_pdf)
        lat.addWidget(novo)
        corpo.addWidget(lateral)

        # ---- principal
        principal = QVBoxLayout()
        principal.setSpacing(14)

        fontes = QHBoxLayout()
        for texto, acao, nome in (
            ("Abrir PDF", self._escolher_pdf, "Abrir um arquivo PDF"),
            ("Abrir imagem", self._escolher_imagem, "Abrir uma imagem e ler o texto dela"),
            ("Ler a tela", self._ler_tela, "Capturar a tela e ler o texto"),
        ):
            b = QPushButton(texto)
            b.setAccessibleName(nome)
            b.clicked.connect(acao)
            fontes.addWidget(b)
        fontes.addStretch(1)
        principal.addLayout(fontes)

        doc = painel()
        dl = QVBoxLayout(doc)
        dl.setContentsMargins(18, 14, 18, 14)
        self.doc_titulo = QLabel("Nenhum documento aberto")
        self.doc_titulo.setStyleSheet("font-size:18px; font-weight:700; border:none;")
        self.doc_info = QLabel("Escolha um PDF, uma imagem ou leia a tela.")
        self.doc_info.setObjectName("textoSuave")
        self.doc_info.setStyleSheet("border:none;")
        dl.addWidget(self.doc_titulo)
        dl.addWidget(self.doc_info)
        principal.addWidget(doc)

        opcoes = painel()
        ol = QHBoxLayout(opcoes)
        ol.setContentsMargins(18, 14, 18, 14)
        ol.setSpacing(18)
        self.modo = combo(MODE_LABELS, "completo", "Modo de leitura")
        self.densidade = combo(DENSITY_LABELS, "medio", "Densidade do resumo")
        self.motor = combo(TTS_LABELS, ctx.config.motor_voz, "Motor de voz")
        ol.addLayout(rotulado("Modo", self.modo))
        ol.addLayout(rotulado("Densidade do resumo", self.densidade))
        ol.addLayout(rotulado("Motor de voz", self.motor))
        self.descrever = QCheckBox("Gerar audiodescrição\n(IA de visão)")
        self.descrever.setChecked(True)
        ol.addLayout(rotulado("Imagens", self.descrever))
        ol.addStretch(1)
        principal.addWidget(opcoes)
        self.modo.currentIndexChanged.connect(self._sincronizar)
        self._sincronizar()

        acoes = QHBoxLayout()
        self.gerar = QPushButton("Gerar leitura")
        self.gerar.setObjectName("botaoPrimario")
        self.gerar.clicked.connect(self._gerar)
        acoes.addWidget(self.gerar)
        self.play = QPushButton("▶")
        self.play.setObjectName("botaoPlay")
        self.play.setFixedSize(72, 72)
        self.play.setAccessibleName("Ouvir o áudio gerado")
        self.play.setEnabled(False)
        self.play.clicked.connect(self._tocar)
        acoes.addWidget(self.play)
        ouvir = QPushButton("Ouvir texto agora")
        ouvir.setAccessibleName("Ler o texto do resultado em voz alta agora")
        ouvir.clicked.connect(lambda: ctx.falador.falar(self.saida.toPlainText()))
        acoes.addWidget(ouvir)
        acoes.addStretch(1)
        principal.addLayout(acoes)

        baixo = QHBoxLayout()
        progresso = QVBoxLayout()
        rp = QLabel("PROGRESSO")
        rp.setObjectName("rotuloSecao")
        progresso.addWidget(rp)
        self.etapas = QListWidget()
        self.etapas.setAccessibleName("Progresso da leitura")
        self.etapas.setMaximumWidth(430)
        progresso.addWidget(self.etapas)
        baixo.addLayout(progresso, 2)
        res = QVBoxLayout()
        rr = QLabel("TEXTO LIDO")
        rr.setObjectName("rotuloSecao")
        res.addWidget(rr)
        self.saida = caixa_resultado("Texto lido")
        res.addWidget(self.saida)
        baixo.addLayout(res, 3)
        principal.addLayout(baixo, 1)

        corpo.addLayout(principal, 1)
        self.raiz.addLayout(corpo, 1)
        self._carregar_recentes()

    # ------------------------------------------------------------------
    def _sincronizar(self) -> None:
        self.densidade.setEnabled(self.modo.currentData() == "resumo")

    def _carregar_recentes(self) -> None:
        self.recentes.clear()
        for caminho in self.ctx.config.pdfs_recentes:
            it = QListWidgetItem(Path(caminho).name)
            it.setData(Qt.UserRole, caminho)
            it.setToolTip(caminho)
            self.recentes.addItem(it)

    def _etapa(self, texto: str, ok: bool | None = True) -> None:
        marca = "[ok]" if ok else ("[...]" if ok is None else "[erro]")
        self.etapas.addItem(f"{marca} {texto}")
        self.etapas.scrollToBottom()

    def _escolher_pdf(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher PDF", "", "PDF (*.pdf)")
        if caminho:
            self._definir_pdf(caminho)

    def _definir_pdf(self, caminho: str) -> None:
        if not caminho or not Path(caminho).exists():
            self.erro(f"Arquivo não encontrado: {caminho}")
            return
        self.pdf_atual = caminho
        self.audio_atual = None
        self.play.setEnabled(False)
        self.ctx.config.lembrar_pdf(caminho)
        self._carregar_recentes()
        self.doc_titulo.setText(Path(caminho).name)
        self.doc_info.setText("Analisando o PDF...")
        self.ctx.anunciar(f"PDF aberto: {Path(caminho).stem}. Pressione Gerar leitura.")
        self.rodar(_info_pdf, caminho, ao_concluir=self.doc_info.setText, estado=None,
                   ao_falhar=lambda m: self.doc_info.setText(f"Não foi possível analisar: {m}"))
        self.gerar.setFocus()

    def _gerar(self) -> None:
        if not self.pdf_atual:
            self._escolher_pdf()
            if not self.pdf_atual:
                return
        if self.worker and self.worker.isRunning():
            return
        cfg = self.ctx.config
        opcoes = ReadingOptions(
            mode=self.modo.currentData(),
            density=self.densidade.currentData(),
            describe_images=self.descrever.isChecked(),
            tts_choice=self.motor.currentData(),
            save_audio=True,
            output_dir=str(Path.home() / "IAVOX_audios"),
            piper_model_path=cfg.piper_model_path or None,
            kokoro_model_path=cfg.kokoro_model_path or None,
            kokoro_voices_path=cfg.kokoro_voices_path or None,
            espeak_binary_path=cfg.espeak_binary_path or None,
        )
        self.etapas.clear()
        self.saida.clear()
        self.gerar.setEnabled(False)
        self.ctx.definir_estado("processando")
        self.ctx.anunciar("Gerando leitura. Aguarde.")

        self.worker = ReaderWorker(self.pdf_atual, opcoes)
        self.worker.reader.extractor.poppler_path = cfg.poppler_path or None
        if cfg.tesseract_cmd:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd
            except ImportError:
                pass
        self._ultima_pagina = 0
        self.worker.progress.connect(self._progresso)
        self.worker.finished_script.connect(lambda s, o=opcoes: self._roteiro(s, o))
        self.worker.finished_audio.connect(self._audio_pronto)
        self.worker.failed.connect(self._falhou)
        self.worker.finished.connect(lambda: self.gerar.setEnabled(True))
        self._etapa("Extraindo texto...", None)
        self.worker.start()

    def _progresso(self, atual: int, total: int, etapa: str) -> None:
        item = self.etapas.item(self.etapas.count() - 1)
        if item and item.text().startswith("[...]"):
            item.setText(f"[...] Página {atual}/{total} — {etapa}")

    def _roteiro(self, script, opcoes: ReadingOptions) -> None:
        ultimo = self.etapas.item(self.etapas.count() - 1)
        if ultimo:
            ocr = " com OCR" if script.used_ocr else " (texto nativo)"
            ultimo.setText(f"[ok] Texto extraído ({script.pages_count} páginas{ocr})")
        if opcoes.mode == "resumo":
            self._etapa(f"Resumo gerado (densidade: {DENSITY_LABELS[opcoes.density].lower()})")
        if opcoes.describe_images:
            self._etapa(f"Audiodescrição: {script.image_descriptions_count} imagem(ns)")
        self._etapa(f"Sintetizando áudio ({TTS_LABELS[opcoes.tts_choice]})...", None)
        self.saida.setPlainText(script.full_text)
        self.ctx.registrar("LeitorVox", f"{Path(self.pdf_atual).name}: {script.full_text}")

    def _audio_pronto(self, caminho: str) -> None:
        self.audio_atual = caminho
        ultimo = self.etapas.item(self.etapas.count() - 1)
        if ultimo:
            ultimo.setText(f"[ok] Áudio salvo em {caminho}")
        self.play.setEnabled(True)
        self.ctx.definir_estado("confirmando")
        self.ctx.anunciar("Leitura pronta. Pressione o botão play para ouvir.")
        self.play.setFocus()

    def _falhou(self, mensagem: str) -> None:
        self._etapa(mensagem, False)
        self.erro(mensagem)

    def _tocar(self) -> None:
        if self.audio_atual:
            self.ctx.falador.calar()
            try:
                self.player.play(self.audio_atual)
            except Exception as exc:  # noqa: BLE001
                self.erro(str(exc))

    # ---- imagem e tela
    def _escolher_imagem(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", "", FILTRO_IMAGENS)
        if caminho:
            self.doc_titulo.setText(Path(caminho).name)
            self.doc_info.setText("Imagem — lendo o texto com OCR...")
            self._ocr(caminho)

    def _ler_tela(self) -> None:
        janela = self.window()
        janela.showMinimized()
        self.ctx.anunciar("Capturando a tela.")
        QTimer.singleShot(900, lambda: self._capturar(janela))

    def _capturar(self, janela) -> None:
        tela = QGuiApplication.primaryScreen()
        foto = tela.grabWindow(0) if tela else QPixmap()
        janela.showNormal()
        janela.activateWindow()
        if foto.isNull():
            self.erro("Não foi possível capturar a tela.")
            return
        caminho = Path(tempfile.gettempdir()) / "iavox_tela.png"
        foto.save(str(caminho), "PNG")
        self.doc_titulo.setText("Captura da tela")
        self.doc_info.setText("Lendo o texto da tela com OCR...")
        self._ocr(str(caminho))

    def _ocr(self, caminho: str) -> None:
        self.saida.clear()
        self.rodar(ler_texto_imagem, caminho, tesseract_cmd=self.ctx.config.tesseract_cmd,
                   ao_concluir=self._ocr_pronto)

    def _ocr_pronto(self, texto: str) -> None:
        if not texto:
            texto = "Nenhum texto encontrado na imagem. Use o OlhaVox (F3) para descrever o que ela mostra."
        self.doc_info.setText(f"{len(texto.split())} palavras reconhecidas")
        self.resultado(self.saida, texto)


def _info_pdf(caminho: str) -> str:
    """Linha de resumo do mockup: '12 páginas · 3 imagens detectadas · texto nativo (sem OCR)'."""
    import pdfplumber

    with pdfplumber.open(caminho) as pdf:
        paginas = len(pdf.pages)
        imagens = sum(len(p.images) for p in pdf.pages)
        amostra = "".join((p.extract_text() or "") for p in pdf.pages[:3])
    tipo = "texto nativo (sem OCR)" if amostra.strip() else "escaneado (vai usar OCR)"
    return f"{paginas} página{'s' if paginas != 1 else ''} · {imagens} imagem(ns) detectada(s) · {tipo}"


# ============================================================ resposta por voz

class RespostaPorVoz(QObject):
    """
    Grava -> transcreve -> pede confirmação. Usado pelo FalaVox e pelo
    Modo Atividade. Sem microfone ou sem Whisper, oferece digitar a resposta.
    """

    estado = pyqtSignal(str)       # gravando | transcrevendo | confirmando | parado
    texto_pronto = pyqtSignal(str)
    falhou = pyqtSignal(str)

    def __init__(self, ctx: Contexto, pai: QWidget):
        super().__init__(pai)
        self.ctx = ctx
        self.pai = pai
        self.gravador: voz_entrada.Gravador | None = None
        self.transcritor = voz_entrada.Transcritor(ctx.config.modelo_whisper)
        self._tarefa: Tarefa | None = None
        self.situacao = "parado"

    def _mudar(self, s: str) -> None:
        self.situacao = s
        self.estado.emit(s)

    def alternar(self) -> None:
        if self.situacao == "gravando":
            self.parar()
        elif self.situacao in ("parado", "confirmando"):
            self.iniciar()

    def iniciar(self) -> None:
        if not voz_entrada.gravacao_disponivel():
            self._digitar("Gravação indisponível: instale o pacote sounddevice (pip install sounddevice). "
                          "Enquanto isso, digite sua resposta.")
            return
        if self.transcritor.modelo_nome != self.ctx.config.modelo_whisper:
            self.transcritor = voz_entrada.Transcritor(self.ctx.config.modelo_whisper)
        self.ctx.falador.calar()
        self.gravador = voz_entrada.Gravador()
        wav = Path(tempfile.gettempdir()) / "iavox_resposta.wav"
        self._mudar("gravando")
        self.ctx.definir_estado("ouvindo")
        self._tarefa = Tarefa(self.gravador.gravar, wav)
        self._tarefa.concluida.connect(self._gravado)
        self._tarefa.falhou.connect(self._erro)
        self._tarefa.start()

    def parar(self) -> None:
        if self.gravador:
            self.gravador.parar()

    def cancelar(self) -> None:
        if self.situacao == "gravando" and self.gravador:
            self._mudar("cancelando")
            self.gravador.parar()
        else:
            self._mudar("parado")
        self.ctx.definir_estado("pronto")

    def _gravado(self, wav) -> None:
        if self.situacao == "cancelando":
            self._mudar("parado")
            return
        if not voz_entrada.transcricao_disponivel():
            self._digitar("Transcrição indisponível: instale o Whisper local (pip install faster-whisper). "
                          "Enquanto isso, digite sua resposta.")
            return
        self._mudar("transcrevendo")
        self.ctx.definir_estado("processando")
        self._tarefa = Tarefa(self.transcritor.transcrever, wav)
        self._tarefa.concluida.connect(self._transcrito)
        self._tarefa.falhou.connect(self._erro)
        self._tarefa.start()

    def _transcrito(self, texto: str) -> None:
        if not texto.strip():
            self._mudar("parado")
            self.ctx.definir_estado("erro")
            self.falhou.emit("Não entendi nenhuma fala. Pressione Ctrl+Shift+M e tente de novo.")
            return
        self._confirmar(texto)

    def _confirmar(self, texto: str) -> None:
        self._mudar("confirmando")
        self.ctx.definir_estado("confirmando")
        self.texto_pronto.emit(texto)

    def _digitar(self, motivo: str) -> None:
        self.ctx.falador.falar(motivo)
        texto, ok = QInputDialog.getMultiLineText(self.pai, "Digite sua resposta", motivo)
        if ok and texto.strip():
            self._confirmar(texto.strip())
        else:
            self._mudar("parado")
            self.ctx.definir_estado("pronto")

    def _erro(self, mensagem: str) -> None:
        self._mudar("parado")
        self.ctx.definir_estado("erro")
        self.falhou.emit(mensagem)


class PainelConfirmacao(QFrame):
    """Tela de confirmação: Enter confirma, Espaço grava de novo, Esc cancela."""

    confirmar = pyqtSignal()
    regravar = pyqtSignal()
    cancelar_ = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("painel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        rot = QLabel("SUA RESPOSTA — CONFIRME")
        rot.setObjectName("rotuloSecao")
        lay.addWidget(rot)
        self.texto = QTextEdit()
        self.texto.setAccessibleName("Resposta transcrita")
        self.texto.setMinimumHeight(110)
        lay.addWidget(self.texto)
        botoes = QHBoxLayout()
        self.b_ok = QPushButton("Confirmar (Enter)")
        self.b_ok.setObjectName("botaoPrimario")
        self.b_ok.clicked.connect(self.confirmar)
        b_de_novo = QPushButton("Gravar de novo (Espaço)")
        b_de_novo.clicked.connect(self.regravar)
        b_cancelar = QPushButton("Cancelar (Esc)")
        b_cancelar.setObjectName("botaoPerigo")
        b_cancelar.clicked.connect(self.cancelar_)
        for b in (self.b_ok, b_de_novo, b_cancelar):
            botoes.addWidget(b)
        botoes.addStretch(1)
        lay.addLayout(botoes)
        # Enter e Espaço valem quando o foco não está editando o texto
        for tecla, sinal in (("Return", self.confirmar), ("Enter", self.confirmar), ("Space", self.regravar)):
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.setContext(Qt.WidgetWithChildrenShortcut)
            atalho.activated.connect(lambda s=sinal: None if self.texto.hasFocus() else s.emit())
        self.hide()

    def mostrar(self, texto: str) -> None:
        self.texto.setPlainText(texto)
        self.show()
        self.b_ok.setFocus()


# ================================================================= F2 Fala

class PaginaFala(PaginaModulo):
    nome_modulo = "FalaVox"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "FalaVox", "Responder com voz: fale, confira a transcrição e envie para o caderno e para o editor do DOSVOX.", "fala", "F2")
        self.voz = RespostaPorVoz(ctx, self)
        self.voz.estado.connect(self._estado)
        self.voz.texto_pronto.connect(self._transcrito)
        self.voz.falhou.connect(self.erro)

        central = painel()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.setSpacing(14)
        self.aviso = QLabel()
        self.aviso.setStyleSheet("font-size:22px; font-weight:700; border:none;")
        self.aviso.setWordWrap(True)
        cl.addWidget(self.aviso)
        self.dica = QLabel()
        self.dica.setObjectName("textoSuave")
        self.dica.setStyleSheet("border:none;")
        self.dica.setWordWrap(True)
        cl.addWidget(self.dica)
        linha = QHBoxLayout()
        self.botao = QPushButton("  Gravar resposta (Ctrl+Shift+M)")
        self.botao.setObjectName("botaoPrimario")
        self.botao.setIcon(_icone_qt("microfone"))
        self.botao.clicked.connect(self.voz.alternar)
        linha.addWidget(self.botao)
        linha.addStretch(1)
        cl.addLayout(linha)
        self.raiz.addWidget(central)

        self.confirmacao = PainelConfirmacao()
        self.confirmacao.confirmar.connect(self._confirmar)
        self.confirmacao.regravar.connect(lambda: self.voz.iniciar())
        self.confirmacao.cancelar_.connect(self.cancelar)
        self.raiz.addWidget(self.confirmacao)

        ult = QLabel("ÚLTIMAS RESPOSTAS ENVIADAS")
        ult.setObjectName("rotuloSecao")
        self.raiz.addWidget(ult)
        self.historico = QListWidget()
        self.historico.setAccessibleName("Últimas respostas enviadas")
        self.raiz.addWidget(self.historico, 1)
        self._estado("parado")

    def _estado(self, s: str) -> None:
        textos = {
            "parado": ("Pronto para ouvir.", "Pressione Ctrl+Shift+M ou o botão abaixo e fale sua resposta. "
                       "Pressione de novo para terminar."),
            "gravando": ("Ouvindo... fale agora.", "Pressione Ctrl+Shift+M para terminar, ou Esc para cancelar."),
            "cancelando": ("Cancelando...", ""),
            "transcrevendo": ("Transcrevendo sua fala...", "O Whisper local está convertendo a voz em texto."),
            "confirmando": ("Confira sua resposta.", "Enter confirma, Espaço grava de novo, Esc cancela."),
        }
        aviso, dica = textos.get(s, ("", ""))
        self.aviso.setText(aviso)
        self.dica.setText(dica)
        self.botao.setText("  Terminar gravação (Ctrl+Shift+M)" if s == "gravando" else "  Gravar resposta (Ctrl+Shift+M)")
        self.botao.setEnabled(s in ("parado", "gravando", "confirmando"))
        if s == "gravando":
            self.ctx.anunciar("Ouvindo.")
        if s != "confirmando":
            self.confirmacao.hide()

    def _transcrito(self, texto: str) -> None:
        self.confirmacao.mostrar(texto)
        self.ctx.falador.falar(f"Você disse: {texto}. Enter confirma, espaço grava de novo.")

    def _confirmar(self) -> None:
        texto = self.confirmacao.texto.toPlainText().strip()
        if not texto:
            return
        QApplication.clipboard().setText(texto)
        arquivo = voz_entrada.inserir_resposta(texto)
        self.ctx.registrar("FalaVox", texto)
        self.historico.insertItem(0, texto)
        self.confirmacao.hide()
        self.voz.situacao = "parado"
        self._estado("parado")
        self.ctx.definir_estado("confirmando")
        editor = " Abra no EDIVOX pelo Mini Caderno." if encontrar_editor_dosvox() else ""
        self.ctx.anunciar(f"Resposta confirmada, copiada e salva em {arquivo.name}.{editor}")
        self.botao.setFocus()

    def ao_entrar(self) -> None:
        self.botao.setFocus()

    def cancelar(self) -> bool:
        if self.voz.situacao in ("gravando", "confirmando", "transcrevendo"):
            self.voz.cancelar()
            self.confirmacao.hide()
            self._estado("parado")
            self.ctx.anunciar("Cancelado.")
            return True
        return False

    def falar_por_voz(self) -> None:
        self.voz.alternar()


# ================================================================= F3 Olha

class PaginaOlha(PaginaModulo):
    nome_modulo = "OlhaVox"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "OlhaVox", "Descrever imagens: fotos, gráficos e figuras são descritos em português pela IA de visão local.", "olho", "F3")
        botoes = QHBoxLayout()
        for texto, acao, nome in (
            ("Abrir imagem", self._abrir, "Abrir uma imagem para descrever"),
            ("Colar imagem (Ctrl+V)", self._colar, "Descrever a imagem copiada"),
            ("Capturar tela", self._tela, "Descrever o que está na tela"),
        ):
            b = QPushButton(texto)
            b.setAccessibleName(nome)
            b.clicked.connect(acao)
            botoes.addWidget(b)
            if texto.startswith("Abrir"):
                self.b_abrir = b
        botoes.addStretch(1)
        self.raiz.addLayout(botoes)
        atalho = QShortcut(QKeySequence.Paste, self)
        atalho.activated.connect(self._colar)

        corpo = QHBoxLayout()
        self.previa = QLabel("Nenhuma imagem")
        self.previa.setAlignment(Qt.AlignCenter)
        self.previa.setObjectName("painel")
        self.previa.setMinimumSize(380, 300)
        self.previa.setAccessibleName("Prévia da imagem")
        corpo.addWidget(self.previa, 2)
        self.saida = caixa_resultado("Descrição da imagem")
        corpo.addWidget(self.saida, 3)
        self.raiz.addLayout(corpo, 1)

    def ao_entrar(self) -> None:
        self.b_abrir.setFocus()

    def _abrir(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", "", FILTRO_IMAGENS)
        if caminho:
            self._descrever(caminho, QPixmap(caminho))

    def _colar(self) -> None:
        img = QApplication.clipboard().image()
        if img.isNull():
            self.ctx.anunciar("Não há imagem copiada.")
            return
        caminho = Path(tempfile.gettempdir()) / "iavox_colada.png"
        img.save(str(caminho), "PNG")
        self._descrever(str(caminho), QPixmap.fromImage(img))

    def _tela(self) -> None:
        janela = self.window()
        janela.showMinimized()
        QTimer.singleShot(900, lambda: self._capturar(janela))

    def _capturar(self, janela) -> None:
        tela = QGuiApplication.primaryScreen()
        foto = tela.grabWindow(0) if tela else QPixmap()
        janela.showNormal()
        janela.activateWindow()
        if foto.isNull():
            self.erro("Não foi possível capturar a tela.")
            return
        caminho = Path(tempfile.gettempdir()) / "iavox_tela.png"
        foto.save(str(caminho), "PNG")
        self._descrever(str(caminho), foto)

    def _descrever(self, caminho: str, previa: QPixmap) -> None:
        self.previa.setPixmap(previa.scaled(self.previa.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.saida.setPlainText("Descrevendo a imagem...")
        self.ctx.anunciar("Descrevendo a imagem. Aguarde.")
        self.rodar(descrever_imagem, caminho, tesseract_cmd=self.ctx.config.tesseract_cmd,
                   ao_concluir=lambda d: self.resultado(self.saida, d.como_fala()))


# ================================================================= F4 Estuda

class PaginaEstuda(PaginaModulo):
    nome_modulo = "EstudaVox"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "EstudaVox", "Resumo e perguntas: abra um PDF ou TXT, ou cole um texto, e receba um resumo e perguntas de estudo.", "livro", "F4")
        self.estudo = None
        self.estudavox = EstudaVox()

        linha = QHBoxLayout()
        self.b_abrir = QPushButton("Abrir PDF ou TXT")
        self.b_abrir.clicked.connect(self._abrir)
        linha.addWidget(self.b_abrir)
        self.densidade = combo(DENSITY_LABELS, "medio", "Tamanho do resumo")
        linha.addLayout(rotulado("Resumo", self.densidade))
        self.qtd = QSpinBox()
        self.qtd.setRange(1, 15)
        self.qtd.setValue(5)
        self.qtd.setAccessibleName("Quantidade de perguntas")
        self.qtd.setStyleSheet(f"background:{theme.AZUL_PAINEL}; border:1px solid {theme.BORDA}; border-radius:10px; padding:8px; font-size:15px;")
        linha.addLayout(rotulado("Perguntas", self.qtd))
        linha.addStretch(1)
        self.raiz.addLayout(linha)

        self.entrada = QTextEdit()
        self.entrada.setAcceptRichText(False)
        self.entrada.setAccessibleName("Texto para estudar")
        self.entrada.setPlaceholderText("Cole aqui o texto para estudar, ou abra um arquivo.")
        self.raiz.addWidget(self.entrada, 2)

        acoes = QHBoxLayout()
        self.b_gerar = QPushButton("Gerar resumo e perguntas")
        self.b_gerar.setObjectName("botaoPrimario")
        self.b_gerar.clicked.connect(self._gerar)
        acoes.addWidget(self.b_gerar)
        self.b_praticar = QPushButton("Praticar no Modo Atividade (F5)")
        self.b_praticar.setEnabled(False)
        self.b_praticar.clicked.connect(self._praticar)
        acoes.addWidget(self.b_praticar)
        acoes.addStretch(1)
        self.raiz.addLayout(acoes)

        self.saida = caixa_resultado("Resumo e perguntas")
        self.raiz.addWidget(self.saida, 3)

    def ao_entrar(self) -> None:
        self.b_abrir.setFocus()

    def _abrir(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "Abrir texto", "", "PDF ou texto (*.pdf *.txt)")
        if caminho:
            self.entrada.setPlainText("Lendo o arquivo...")
            self.rodar(ler_texto_de_arquivo, caminho, estado="processando",
                       ao_concluir=self._texto_carregado)

    def _texto_carregado(self, texto: str) -> None:
        self.entrada.setPlainText(texto)
        self.ctx.definir_estado("pronto")
        self.ctx.anunciar(f"Arquivo carregado, {len(texto.split())} palavras. Pressione Gerar resumo e perguntas.")
        self.b_gerar.setFocus()

    def _gerar(self) -> None:
        texto = self.entrada.toPlainText().strip()
        if not texto:
            self.erro("Abra um arquivo ou cole um texto primeiro.")
            return
        self.b_gerar.setEnabled(False)
        self.ctx.anunciar("Gerando resumo e perguntas. Aguarde.")
        t = self.rodar(self.estudavox.estudar, texto, self.densidade.currentData(), self.qtd.value(),
                       ao_concluir=self._pronto)
        t.finished.connect(lambda: self.b_gerar.setEnabled(True))

    def _pronto(self, estudo) -> None:
        self.estudo = estudo
        self.ctx.perguntas = list(estudo.perguntas)
        self.b_praticar.setEnabled(bool(estudo.perguntas))
        aviso = "" if estudo.usou_ia else "\n\n(Sem IA local: resumo e perguntas simples. Instale o Ollama para melhores resultados.)"
        self.resultado(self.saida, estudo.como_texto() + aviso, falar=estudo.como_fala())

    def _praticar(self) -> None:
        self.ctx.navegar("atividade")


# ============================================================ F5 Atividade

class PaginaAtividade(PaginaModulo):
    nome_modulo = "Atividade"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "Modo Atividade", "Ouvir, responder, confirmar e continuar: o IAVOX lê cada pergunta, você responde com a voz e confirma.", "estrela", "F5")
        self.perguntas: list[str] = []
        self.indice = 0
        self.respostas: list[tuple[str, str]] = []

        linha = QHBoxLayout()
        self.b_carregar = QPushButton("Carregar perguntas (TXT, uma por linha)")
        self.b_carregar.clicked.connect(self._carregar)
        linha.addWidget(self.b_carregar)
        self.b_estuda = QPushButton("Usar perguntas do EstudaVox")
        self.b_estuda.clicked.connect(self._do_estuda)
        linha.addWidget(self.b_estuda)
        linha.addStretch(1)
        self.raiz.addLayout(linha)

        cartao = QFrame()
        cartao.setObjectName("cartaoDestaque")
        cl = QVBoxLayout(cartao)
        cl.setContentsMargins(26, 20, 26, 20)
        self.contador = QLabel("Nenhuma atividade carregada")
        self.contador.setStyleSheet(f"color:{theme.AMARELO_FOCO}; font-size:16px; font-weight:700; border:none;")
        self.pergunta = QLabel("Carregue um arquivo de perguntas ou gere perguntas no EstudaVox (F4).")
        self.pergunta.setWordWrap(True)
        self.pergunta.setStyleSheet("font-size:24px; font-weight:600; border:none;")
        self.pergunta.setFocusPolicy(Qt.StrongFocus)
        self.pergunta.setAccessibleName("Pergunta atual")
        cl.addWidget(self.contador)
        cl.addWidget(self.pergunta)
        botoes = QHBoxLayout()
        self.b_ouvir = QPushButton("Ouvir pergunta")
        self.b_ouvir.clicked.connect(self._ler_pergunta)
        self.b_responder = QPushButton("  Responder com voz (Ctrl+Shift+M)")
        self.b_responder.setObjectName("botaoPrimario")
        self.b_responder.setIcon(_icone_qt("microfone"))
        self.b_pular = QPushButton("Pular")
        self.b_pular.clicked.connect(self._proxima)
        for b in (self.b_ouvir, self.b_responder, self.b_pular):
            b.setEnabled(False)
            botoes.addWidget(b)
        botoes.addStretch(1)
        cl.addLayout(botoes)
        self.raiz.addWidget(cartao)

        self.voz = RespostaPorVoz(ctx, self)
        self.b_responder.clicked.connect(self.voz.alternar)
        self.voz.estado.connect(self._estado_voz)
        self.voz.texto_pronto.connect(self._transcrito)
        self.voz.falhou.connect(self.erro)
        self.confirmacao = PainelConfirmacao()
        self.confirmacao.confirmar.connect(self._confirmar)
        self.confirmacao.regravar.connect(lambda: self.voz.iniciar())
        self.confirmacao.cancelar_.connect(self.cancelar)
        self.raiz.addWidget(self.confirmacao)

        rot = QLabel("RESPOSTAS DESTA ATIVIDADE")
        rot.setObjectName("rotuloSecao")
        self.raiz.addWidget(rot)
        self.lista = QListWidget()
        self.lista.setAccessibleName("Respostas desta atividade")
        self.raiz.addWidget(self.lista, 1)

    def ao_entrar(self) -> None:
        perguntas = getattr(self.ctx, "perguntas", None)
        if perguntas and not self.perguntas:
            self.iniciar(perguntas)
        elif self.perguntas:
            self.pergunta.setFocus()
        else:
            self.b_carregar.setFocus()

    def _do_estuda(self) -> None:
        perguntas = getattr(self.ctx, "perguntas", None)
        if not perguntas:
            self.erro("Ainda não há perguntas do EstudaVox. Abra o EstudaVox (F4) e gere perguntas.")
            return
        self.iniciar(perguntas)

    def _carregar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "Arquivo de perguntas", "", "Texto (*.txt)")
        if not caminho:
            return
        texto = ler_texto_de_arquivo(caminho)
        perguntas = [l.strip(" -•\t") for l in texto.splitlines() if l.strip(" -•\t")]
        if not perguntas:
            self.erro("O arquivo não tem perguntas.")
            return
        self.iniciar(perguntas)

    def iniciar(self, perguntas: list[str]) -> None:
        self.perguntas = list(perguntas)
        self.indice = 0
        self.respostas = []
        self.lista.clear()
        for b in (self.b_ouvir, self.b_responder, self.b_pular):
            b.setEnabled(True)
        self._mostrar()

    def _mostrar(self) -> None:
        if self.indice >= len(self.perguntas):
            self._concluir()
            return
        self.contador.setText(f"PERGUNTA {self.indice + 1} DE {len(self.perguntas)}")
        self.pergunta.setText(self.perguntas[self.indice])
        self.confirmacao.hide()
        self.ctx.definir_estado("pronto")
        self._ler_pergunta()
        self.b_responder.setFocus()

    def _ler_pergunta(self) -> None:
        if self.perguntas and self.indice < len(self.perguntas):
            self.ctx.falador.falar(
                f"Pergunta {self.indice + 1} de {len(self.perguntas)}. {self.perguntas[self.indice]}. "
                "Para responder, pressione Control Shift M."
            )

    def _estado_voz(self, s: str) -> None:
        self.b_responder.setText("  Terminar gravação (Ctrl+Shift+M)" if s == "gravando"
                                 else "  Responder com voz (Ctrl+Shift+M)")

    def _transcrito(self, texto: str) -> None:
        self.confirmacao.mostrar(texto)
        self.ctx.falador.falar(f"Você respondeu: {texto}. Enter confirma, espaço grava de novo.")

    def _confirmar(self) -> None:
        resposta = self.confirmacao.texto.toPlainText().strip()
        if not resposta:
            return
        pergunta = self.perguntas[self.indice]
        self.respostas.append((pergunta, resposta))
        self.lista.addItem(f"{self.indice + 1}. {pergunta} — {resposta}")
        self.ctx.registrar("Atividade", f"Pergunta: {pergunta}\nResposta: {resposta}")
        self.voz.situacao = "parado"
        self.ctx.definir_estado("confirmando")
        self.indice += 1
        self.ctx.anunciar("Resposta confirmada.")
        QTimer.singleShot(1200, self._mostrar)

    def _proxima(self) -> None:
        self.voz.cancelar()
        self.indice += 1
        self._mostrar()

    def _concluir(self) -> None:
        self.contador.setText("ATIVIDADE CONCLUÍDA")
        self.pergunta.setText(f"Você respondeu {len(self.respostas)} de {len(self.perguntas)} perguntas. "
                              "As respostas estão no Mini Caderno.")
        for b in (self.b_ouvir, self.b_responder, self.b_pular):
            b.setEnabled(False)
        self.ctx.definir_estado("confirmando")
        self.ctx.anunciar(self.pergunta.text())
        self.perguntas = []
        self.ctx.perguntas = None
        self.b_carregar.setFocus()

    def cancelar(self) -> bool:
        if self.voz.situacao in ("gravando", "confirmando", "transcrevendo"):
            self.voz.cancelar()
            self.confirmacao.hide()
            self.ctx.anunciar("Resposta cancelada.")
            self.b_responder.setFocus()
            return True
        return False

    def falar_por_voz(self) -> None:
        if self.perguntas:
            self.voz.alternar()


# ============================================================ Mini Caderno

class PaginaCaderno(PaginaModulo):
    nome_modulo = "Caderno"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "Mini Caderno", "Registro cronológico do que foi feito, para o professor acompanhar. Texto leve, até 30 itens na tela.", "atividade", "")
        botoes = QHBoxLayout()
        self.b_ler = QPushButton("Ler Caderno")
        self.b_ler.clicked.connect(lambda: ctx.falador.falar(ctx.caderno.como_fala()))
        b_txt = QPushButton("Salvar TXT")
        b_txt.clicked.connect(self._salvar)
        b_ed = QPushButton("Abrir no EDIVOX")
        b_ed.setAccessibleName("Abrir o caderno no editor do DOSVOX")
        b_ed.clicked.connect(self._abrir_editor)
        b_limpar = QPushButton("Limpar")
        b_limpar.setObjectName("botaoPerigo")
        b_limpar.clicked.connect(self._limpar)
        for b in (self.b_ler, b_txt, b_ed, b_limpar):
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.contagem = QLabel()
        self.contagem.setObjectName("textoSuave")
        botoes.addWidget(self.contagem)
        self.raiz.addLayout(botoes)

        self.lista = QListWidget()
        self.lista.setAccessibleName("Itens do Mini Caderno")
        self.lista.setWordWrap(True)
        self.lista.itemActivated.connect(lambda it: ctx.falador.falar(it.data(Qt.UserRole)))
        self.raiz.addWidget(self.lista, 1)
        dica = QLabel("Enter em um item lê o texto completo.")
        dica.setObjectName("textoSuave")
        self.raiz.addWidget(dica)
        self.atualizar()

    def atualizar(self) -> None:
        self.lista.clear()
        itens = self.ctx.caderno.itens_na_tela()
        for item in itens:
            w = QListWidgetItem(f"{item.modulo}   ·   {item.data_hora}\n{item.resumo}")
            w.setData(Qt.UserRole, f"{item.modulo}, {item.data_hora}. {item.texto}")
            w.setIcon(_icone_modulo(item.modulo))
            self.lista.addItem(w)
        total = len(self.ctx.caderno.itens)
        self.contagem.setText(f"Mostrando {len(itens)} de {total} itens")

    def ao_entrar(self) -> None:
        self.atualizar()
        if self.lista.count():
            self.lista.setCurrentRow(0)
            self.lista.setFocus()
        else:
            self.b_ler.setFocus()

    def _arquivo_txt(self) -> Path:
        return Path.home() / "IAVOX_caderno.txt"

    def _salvar(self) -> None:
        destino, _ = QFileDialog.getSaveFileName(self, "Salvar caderno", str(self._arquivo_txt()), "Texto (*.txt)")
        if destino:
            self.ctx.caderno.salvar_txt(destino)
            self.ctx.anunciar(f"Caderno salvo em {Path(destino).name}.")

    def _abrir_editor(self) -> None:
        caminho = self.ctx.caderno.salvar_txt(self._arquivo_txt())
        try:
            programa = abrir_no_editor(caminho)
            self.ctx.anunciar(f"Caderno aberto no {programa}.")
        except Exception as exc:  # noqa: BLE001
            self.erro(f"Não foi possível abrir o editor: {exc}")

    def _limpar(self) -> None:
        if QMessageBox.question(self, "Limpar caderno", "Apagar todos os itens do Mini Caderno?") == QMessageBox.Yes:
            self.ctx.caderno.limpar()
            self.atualizar()
            self.ctx.anunciar("Caderno limpo.")


def _icone_modulo(modulo: str):
    from .icones import icone
    nome = {"LeitorVox": "documento", "FalaVox": "fala", "OlhaVox": "olho",
            "EstudaVox": "livro", "Atividade": "estrela"}.get(modulo, "documento")
    return icone(nome, 32)


# ================================================================== Ajuda

AJUDA_HTML = f"""
<h2 style='color:{theme.AZUL_ELETRICO}'>Teclado</h2>
<table cellpadding='6'>
<tr><td><b>F1</b></td><td>LeitorVox — ler PDF, imagem ou a tela</td></tr>
<tr><td><b>F2</b></td><td>FalaVox — responder com a voz</td></tr>
<tr><td><b>F3</b></td><td>OlhaVox — descrever imagens</td></tr>
<tr><td><b>F4</b></td><td>EstudaVox — resumo e perguntas</td></tr>
<tr><td><b>F5</b></td><td>Modo Atividade — ouvir, responder, confirmar e continuar</td></tr>
<tr><td><b>Ctrl+Shift+M</b></td><td>começar e terminar a gravação da resposta</td></tr>
<tr><td><b>Enter</b></td><td>confirmar a resposta</td></tr>
<tr><td><b>Espaço</b></td><td>gravar a resposta de novo</td></tr>
<tr><td><b>Esc</b></td><td>cancelar; se não houver nada para cancelar, volta ao início</td></tr>
<tr><td><b>Ctrl+R</b></td><td>repetir a última mensagem falada</td></tr>
<tr><td><b>Ctrl+.</b></td><td>calar a voz</td></tr>
<tr><td><b>Tab</b></td><td>passar pelos botões (o foco fica em amarelo)</td></tr>
</table>
<h2 style='color:{theme.AZUL_ELETRICO}'>Estados do robô</h2>
<p>{'<br>'.join(f"<b>{n}</b> — {d}" for n, d, _ in ESTADOS_ROBO.values())}</p>
<p>O estado também aparece escrito e é anunciado ao leitor de tela.</p>
<h2 style='color:{theme.AZUL_ELETRICO}'>O que instalar (tudo offline)</h2>
<p><b>Voz:</b> espeak-ng (obrigatório); Piper ou Kokoro para voz mais natural.<br>
<b>OCR:</b> Tesseract com idioma português.<br>
<b>Resumo, perguntas e descrição de imagens:</b> Ollama com <i>llama3.2:3b</i> e <i>llava:7b</i>.<br>
<b>Responder com voz:</b> <i>pip install sounddevice faster-whisper</i> (o modelo do Whisper é baixado
na primeira vez e depois funciona sem internet).</p>
<p>A barra de baixo mostra, em verde, o que já está funcionando neste computador.
Pressione Enter em um item para ouvir o detalhe.</p>
"""


class PaginaAjuda(PaginaModulo):
    nome_modulo = "Ajuda"

    def __init__(self, ctx: Contexto):
        super().__init__(ctx, "Ajuda", "Atalhos de teclado, estados do robô e o que instalar.", "ajuda", "")
        self.texto = QTextBrowser()
        self.texto.setAccessibleName("Texto de ajuda")
        self.texto.setHtml(AJUDA_HTML)
        self.texto.setStyleSheet("font-size:17px;")
        self.raiz.addWidget(self.texto, 1)

    def ao_entrar(self) -> None:
        self.texto.setFocus()
