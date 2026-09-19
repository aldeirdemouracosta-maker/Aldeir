#!/usr/bin/env python3
"""Interface desktop da fábrica local de IA — janela única, minimalista.

Reaproveita `analisador_projeto` e `orquestrador` como bibliotecas
Python (não via CLI): escolhe uma pasta de projeto, mostra o
diagnóstico de completude, recebe uma instrução em linguagem natural e
roda o orquestrador. Chamadas ao modelo e ao analisador rodam em
QThread separada — a janela não trava enquanto o modelo responde
(pode levar minutos em hardware sem GPU dedicada de sobra).

Uso:
    python3 -m interface.janela_principal
"""

import json
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from analisador_projeto.analisar_completude import analisar_completude, formatar_diagnostico_para_prompt
from geracao_mockup.gerar_mockup_simples import gerar_mockup_simples
from importador_zip.inspecionar_zip import analisar_projeto as analisar_zip
from motor_ia.selecionar_motor import (
    encerrar_processos_llama_server,
    listar_processos_llama_server,
    temperatura_gpu_celsius,
)
from orquestrador.orquestrador import ExecucaoInterrompidaError, Orquestrador
from visao_mockup.interpretar_mockup import interpretar_mockup as interpretar_mockup_imagem

FONTE_MONO = "Menlo, Consolas, 'DejaVu Sans Mono', monospace"

EXEMPLOS_INSTRUCAO = [
    "Termine a implementação pendente.",
    "Corrija os testes que estão falhando, sem alterar o comportamento esperado.",
    "Implemente a tela descrita no mockup, seguindo a descrição acima como referência.",
    "Adicione tratamento de erro nas funções que ainda não têm.",
    "Revise o código em busca de bugs simples e corrija os que encontrar.",
    "Adicione testes automatizados para as funções sem cobertura.",
]


class TrabalhadorAnalise(QObject):
    concluido = Signal(dict)
    erro = Signal(str)

    def __init__(self, diretorio: Path):
        super().__init__()
        self.diretorio = diretorio

    def rodar(self) -> None:
        try:
            relatorio = analisar_completude(self.diretorio, rodar_testes_automaticos=False)
            self.concluido.emit(asdict(relatorio))
        except Exception as erro:  # noqa: BLE001 — qualquer falha vira erro visível na UI, não crash silencioso
            self.erro.emit(f"{type(erro).__name__}: {erro}")


class TrabalhadorImportacaoZip(QObject):
    concluido = Signal(dict)
    erro = Signal(str)

    def __init__(self, caminho_zip: Path):
        super().__init__()
        self.caminho_zip = caminho_zip

    def rodar(self) -> None:
        try:
            diretorio_trabalho = Path(tempfile.mkdtemp(prefix="fabrica_local_ia_zip_"))
            relatorio = analisar_zip(self.caminho_zip, diretorio_trabalho)
            self.concluido.emit(asdict(relatorio))
        except Exception as erro:  # noqa: BLE001 — inclui ZipInseguroError: some vira erro visível na UI
            self.erro.emit(f"{type(erro).__name__}: {erro}")


class TrabalhadorDescricaoMockup(QObject):
    concluido = Signal(str)
    erro = Signal(str)

    def __init__(self, binario: Path, modelo: Path, mmproj: Path, imagem: Path):
        super().__init__()
        self.binario = binario
        self.modelo = modelo
        self.mmproj = mmproj
        self.imagem = imagem

    def rodar(self) -> None:
        try:
            descricao = interpretar_mockup_imagem(self.binario, self.modelo, self.mmproj, self.imagem)
            self.concluido.emit(descricao)
        except Exception as erro:  # noqa: BLE001 — inclui ServidorVisaoIndisponivelError: vira erro visível na UI
            self.erro.emit(f"{type(erro).__name__}: {erro}")


class TrabalhadorOrquestrador(QObject):
    evento = Signal(str)
    concluido = Signal(dict)
    erro = Signal(str)
    interrompido = Signal()

    def __init__(
        self,
        diretorio: Path,
        instrucao: str,
        contexto_extra: Optional[str],
        caminho_binario_busca: Optional[Path] = None,
        caminho_modelo_busca: Optional[Path] = None,
    ):
        super().__init__()
        self.diretorio = diretorio
        self.instrucao = instrucao
        self.contexto_extra = contexto_extra
        self.caminho_binario_busca = caminho_binario_busca
        self.caminho_modelo_busca = caminho_modelo_busca
        self._parar_solicitado = False

    def solicitar_parada(self) -> None:
        """Chamado pela thread principal (botão "Parar…") — só marca um
        sinalizador; o loop do orquestrador é quem checa e para sozinho
        entre chamadas, então uma chamada ao modelo já em andamento
        termina normalmente antes de parar."""
        self._parar_solicitado = True

    def rodar(self) -> None:
        try:
            orquestrador = Orquestrador(
                self.diretorio,
                caminho_binario_busca=self.caminho_binario_busca,
                caminho_modelo_busca=self.caminho_modelo_busca,
            )
            resultado = orquestrador.rodar(
                self.instrucao,
                contexto_extra=self.contexto_extra,
                on_evento=self.evento.emit,
                deve_parar=lambda: self._parar_solicitado,
            )
            self.concluido.emit(resultado)
        except ExecucaoInterrompidaError:
            self.interrompido.emit()
        except Exception as erro:  # noqa: BLE001 — idem: erro visível na UI, nunca trava sem explicação
            self.erro.emit(f"{type(erro).__name__}: {erro}")


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fábrica Local de IA")
        self.resize(820, 640)

        self._ultimo_diagnostico: Optional[dict] = None
        self._ultima_descricao_mockup: Optional[str] = None
        self._ultimo_mockup_gerado: Optional[Path] = None
        self._destino_zip_pendente: Optional[str] = None
        self._thread: Optional[QThread] = None
        self._trabalhador: Optional[QObject] = None
        self._configuracoes = QSettings("FabricaLocalIA", "Interface")

        self._montar_widgets()
        self._restaurar_layout()

    # ---- construção da UI --------------------------------------------------

    def _montar_widgets(self) -> None:
        centro = QWidget()
        layout = QVBoxLayout(centro)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Pasta do projeto"))
        linha_pasta = QHBoxLayout()
        self.campo_pasta = QLineEdit()
        self.campo_pasta.setPlaceholderText("/caminho/do/projeto")
        self.botao_procurar = QPushButton("Procurar…")
        self.botao_procurar.clicked.connect(self._escolher_pasta)
        self.botao_abrir_zip = QPushButton("Abrir ZIP…")
        self.botao_abrir_zip.clicked.connect(self._escolher_zip)
        self.botao_gerar_mockup_simples = QPushButton("Gerar mockup simples…")
        self.botao_gerar_mockup_simples.setToolTip(
            "Desenha um wireframe genérico local — sem IA, sem GPU, instantâneo — "
            "como ponto de partida. Use \"Descrever mockup…\" depois para interpretá-lo."
        )
        self.botao_gerar_mockup_simples.clicked.connect(self._gerar_mockup_simples)
        linha_pasta.addWidget(self.campo_pasta)
        linha_pasta.addWidget(self.botao_procurar)
        linha_pasta.addWidget(self.botao_abrir_zip)
        linha_pasta.addWidget(self.botao_gerar_mockup_simples)
        layout.addLayout(linha_pasta)

        layout.addWidget(QLabel("Elementos do mockup simples (opcional — uma linha por elemento; vazio usa lista padrão)"))
        self.campo_elementos_mockup = QPlainTextEdit()
        self.campo_elementos_mockup.setPlaceholderText("ex.: Campo usuário\nBotão Entrar")
        self.campo_elementos_mockup.setFixedHeight(50)
        layout.addWidget(self.campo_elementos_mockup)

        linha_acoes_diag = QHBoxLayout()
        self.botao_analisar = QPushButton("Analisar projeto")
        self.botao_analisar.clicked.connect(self._analisar_projeto)
        self.botao_usar_mesmo_assim = QPushButton("Usar pasta extraída mesmo assim")
        self.botao_usar_mesmo_assim.clicked.connect(self._usar_extraido_mesmo_assim)
        self.botao_usar_mesmo_assim.setVisible(False)
        linha_acoes_diag.addWidget(self.botao_analisar)
        linha_acoes_diag.addWidget(self.botao_usar_mesmo_assim)
        linha_acoes_diag.addStretch()
        layout.addLayout(linha_acoes_diag)

        linha_mockup = QHBoxLayout()
        self.botao_descrever_mockup = QPushButton("Descrever mockup…")
        self.botao_descrever_mockup.setToolTip(
            "Sobe um modelo de visão temporário para ler uma imagem de mockup. "
            "Desligue o modelo de código antes — os dois não cabem na mesma GPU."
        )
        self.botao_descrever_mockup.clicked.connect(self._descrever_mockup)
        self.botao_redefinir_visao = QPushButton("Redefinir caminhos…")
        self.botao_redefinir_visao.setToolTip(
            "Esquece o executável/modelo/mmproj salvos para o modelo de visão — "
            "use se apontou um caminho errado por engano."
        )
        self.botao_redefinir_visao.clicked.connect(self._redefinir_caminhos_visao)
        self.rotulo_mockup = QLabel("Nenhuma descrição de mockup carregada.")
        linha_mockup.addWidget(self.botao_descrever_mockup)
        linha_mockup.addWidget(self.botao_redefinir_visao)
        linha_mockup.addWidget(self.rotulo_mockup, stretch=1)
        layout.addLayout(linha_mockup)

        linha_instrucao = QHBoxLayout()
        linha_instrucao.addWidget(QLabel("Instrução"))
        self.combo_exemplos_instrucao = QComboBox()
        self.combo_exemplos_instrucao.addItem("Exemplos de instrução…")
        self.combo_exemplos_instrucao.addItems(EXEMPLOS_INSTRUCAO)
        self.combo_exemplos_instrucao.setToolTip(
            "Escolher um exemplo substitui o texto atual do campo Instrução."
        )
        self.combo_exemplos_instrucao.currentIndexChanged.connect(self._aplicar_exemplo_instrucao)
        linha_instrucao.addWidget(self.combo_exemplos_instrucao, stretch=1)
        layout.addLayout(linha_instrucao)

        self.campo_instrucao = QPlainTextEdit()
        self.campo_instrucao.setPlaceholderText("ex.: termine a implementação pendente")
        self.campo_instrucao.setFixedHeight(70)
        layout.addWidget(self.campo_instrucao)

        linha_executar = QHBoxLayout()
        self.botao_executar = QPushButton("Executar")
        self.botao_executar.clicked.connect(self._executar_orquestrador)
        self.botao_parar = QPushButton("Parar")
        self.botao_parar.setToolTip(
            "Pede para o orquestrador parar antes da próxima chamada ao modelo ou "
            "ferramenta — não interrompe uma chamada já em andamento."
        )
        self.botao_parar.setEnabled(False)
        self.botao_parar.clicked.connect(self._parar_orquestrador)
        self.botao_configurar_busca = QPushButton("Configurar busca semântica…")
        self.botao_configurar_busca.setToolTip(
            "Aponta o llama-server e o modelo de embeddings (ex.: CodeRankEmbed) — "
            "opcional, habilita a ferramenta buscar_codigo pro agente. Sem isso "
            "configurado, o Executar funciona normalmente, só sem essa ferramenta."
        )
        self.botao_configurar_busca.clicked.connect(self._configurar_busca_semantica)
        self.botao_verificar_gpu = QPushButton("Verificar configuração da GPU")
        self.botao_verificar_gpu.setToolTip(
            "Lista processos llama-server rodando agora e avisa se algum foi "
            "iniciado sem limite de camadas na GPU (-ngl) — sem isso, sob carga "
            "sustentada o driver pode travar (visto na prática nesta máquina)."
        )
        self.botao_verificar_gpu.clicked.connect(self._verificar_configuracao_gpu)
        self.botao_encerrar_gpu = QPushButton("Encerrar todos os llama-server")
        self.botao_encerrar_gpu.setToolTip(
            "Botão de emergência: manda SIGTERM em todo processo llama-server "
            "encontrado, inclusive um servidor de código/visão que você tenha "
            "subido manualmente. Usa antes de qualquer chamada em andamento no "
            "aplicativo falhar. Pede confirmação antes de agir."
        )
        self.botao_encerrar_gpu.clicked.connect(self._encerrar_llama_server)
        linha_executar.addWidget(self.botao_executar)
        linha_executar.addWidget(self.botao_parar)
        linha_executar.addWidget(self.botao_configurar_busca)
        linha_executar.addWidget(self.botao_verificar_gpu)
        linha_executar.addWidget(self.botao_encerrar_gpu)
        layout.addLayout(linha_executar)

        self.rotulo_status = QLabel("")
        layout.addWidget(self.rotulo_status)

        self.setCentralWidget(centro)

        # Diagnóstico e Progresso são painéis dockáveis: o usuário pode
        # arrastar, flutuar ou reorganizar onde quiser — o arranjo é
        # lembrado entre sessões (ver _restaurar_layout/closeEvent).
        self.area_diagnostico = QPlainTextEdit()
        self.area_diagnostico.setReadOnly(True)
        self.area_diagnostico.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.area_diagnostico.setMaximumBlockCount(2000)
        self.dock_diagnostico = QDockWidget("Diagnóstico", self)
        self.dock_diagnostico.setObjectName("dock_diagnostico")
        self.dock_diagnostico.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.dock_diagnostico.setWidget(self.area_diagnostico)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_diagnostico)

        self.area_log = QPlainTextEdit()
        self.area_log.setReadOnly(True)
        self.area_log.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.area_log.setMaximumBlockCount(5000)
        self.dock_progresso = QDockWidget("Progresso", self)
        self.dock_progresso.setObjectName("dock_progresso")
        self.dock_progresso.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.dock_progresso.setWidget(self.area_log)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_progresso)

        # "Código" mostra o conteúdo de cada escrever_arquivo formatado
        # (quebras de linha reais, sem escape de JSON) — a mesma informação
        # já aparece no Progresso, só que ilegível numa linha só de JSON.
        self.area_codigo = QPlainTextEdit()
        self.area_codigo.setReadOnly(True)
        self.area_codigo.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.dock_codigo = QDockWidget("Código", self)
        self.dock_codigo.setObjectName("dock_codigo")
        self.dock_codigo.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.dock_codigo.setWidget(self.area_codigo)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_codigo)
        self.tabifyDockWidget(self.dock_diagnostico, self.dock_codigo)

        # "Relatórios" acumula erros/falhas entre execuções (não é limpo a
        # cada "Executar" como o Progresso) — histórico pra achar rápido
        # qual arquivo/comando causou um erro, sem procurar no log inteiro.
        self.area_relatorios = QPlainTextEdit()
        self.area_relatorios.setReadOnly(True)
        self.area_relatorios.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.area_relatorios.setMaximumBlockCount(2000)
        self.dock_relatorios = QDockWidget("Relatórios", self)
        self.dock_relatorios.setObjectName("dock_relatorios")
        self.dock_relatorios.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.dock_relatorios.setWidget(self.area_relatorios)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_relatorios)
        self.tabifyDockWidget(self.dock_progresso, self.dock_relatorios)

        self._ultima_ferramenta_chamada: Optional[str] = None

    # ---- layout dos painéis (dock widgets) -----------------------------------

    def _restaurar_layout(self) -> None:
        geometria = self._configuracoes.value("janela/geometria")
        if geometria is not None:
            self.restoreGeometry(geometria)
        estado = self._configuracoes.value("janela/estado_docks")
        if estado is not None:
            self.restoreState(estado)

    def closeEvent(self, evento) -> None:  # noqa: N802 — nome exigido pelo Qt
        self._configuracoes.setValue("janela/geometria", self.saveGeometry())
        self._configuracoes.setValue("janela/estado_docks", self.saveState())
        super().closeEvent(evento)

    # ---- pasta do projeto ---------------------------------------------------

    def _definir_pasta_projeto(self, pasta: str) -> None:
        """Troca a pasta do projeto e esquece diagnóstico/descrição de
        mockup da pasta anterior — sem isso, trocar de projeto sem clicar
        em "Analisar projeto" de novo faz o "Executar" usar contexto de
        um projeto diferente (visto na prática: resumo citando arquivos
        da Fábrica ao rodar sobre outro projeto)."""
        self.campo_pasta.setText(pasta)
        self._ultimo_diagnostico = None
        self._ultima_descricao_mockup = None
        self.area_diagnostico.clear()
        self.rotulo_mockup.setText("Nenhuma descrição de mockup carregada.")

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Escolher pasta do projeto")
        if pasta:
            self._definir_pasta_projeto(pasta)

    def _escolher_zip(self) -> None:
        caminho_texto, _ = QFileDialog.getOpenFileName(self, "Abrir projeto em ZIP", "", "Arquivos ZIP (*.zip)")
        if not caminho_texto:
            return

        self.botao_usar_mesmo_assim.setVisible(False)
        self._destino_zip_pendente = None
        self.botao_abrir_zip.setEnabled(False)
        self.area_log.clear()
        self.area_log.appendPlainText(f"Importando ZIP: {caminho_texto}")
        self.rotulo_status.setText("Extraindo e verificando o ZIP…")

        thread = QThread(self)
        trabalhador = TrabalhadorImportacaoZip(Path(caminho_texto))
        trabalhador.moveToThread(thread)
        thread.started.connect(trabalhador.rodar)
        trabalhador.concluido.connect(self._zip_importado)
        trabalhador.erro.connect(self._zip_com_erro)
        trabalhador.concluido.connect(thread.quit)
        trabalhador.erro.connect(thread.quit)
        thread.finished.connect(lambda: self.botao_abrir_zip.setEnabled(True))

        self._thread_zip = thread
        self._trabalhador_zip = trabalhador
        thread.start()

    def _zip_importado(self, relatorio: dict) -> None:
        destino = relatorio["diretorio_extraido"]
        riscos = relatorio["arquivos_de_risco"] + relatorio["padroes_suspeitos"]

        self.area_log.appendPlainText(
            f"{relatorio['total_arquivos']} arquivo(s), {relatorio['total_bytes']} byte(s) extraídos."
        )
        for risco in riscos:
            self.area_log.appendPlainText(f"  risco: {risco['arquivo']} — {risco['motivo']}")

        if relatorio["pode_auto_prosseguir"]:
            self._definir_pasta_projeto(destino)
            self.rotulo_status.setText("ZIP importado — sem riscos detectados.")
        else:
            self._destino_zip_pendente = destino
            self.botao_usar_mesmo_assim.setVisible(True)
            self.rotulo_status.setText(
                "ZIP tem itens que precisam de revisão — ver log acima antes de continuar."
            )

    def _zip_com_erro(self, mensagem: str) -> None:
        self.area_log.appendPlainText(f"Erro ao importar ZIP: {mensagem}")
        self.rotulo_status.setText("Falha ao importar o ZIP — ver log acima.")

    def _usar_extraido_mesmo_assim(self) -> None:
        if self._destino_zip_pendente:
            self._definir_pasta_projeto(self._destino_zip_pendente)
            self.rotulo_status.setText("Usando pasta extraída do ZIP apesar dos itens sinalizados.")
        self.botao_usar_mesmo_assim.setVisible(False)
        self._destino_zip_pendente = None

    def _diretorio_projeto(self) -> Optional[Path]:
        texto = self.campo_pasta.text().strip()
        if not texto:
            self.rotulo_status.setText("Escolha uma pasta de projeto primeiro.")
            return None
        caminho = Path(texto)
        if not caminho.is_dir():
            self.rotulo_status.setText(f"Pasta não encontrada: {caminho}")
            return None
        return caminho

    # ---- analisar projeto ---------------------------------------------------

    def _analisar_projeto(self) -> None:
        diretorio = self._diretorio_projeto()
        if diretorio is None:
            return

        self.botao_analisar.setEnabled(False)
        self.rotulo_status.setText("Analisando projeto…")

        thread = QThread(self)
        trabalhador = TrabalhadorAnalise(diretorio)
        trabalhador.moveToThread(thread)
        thread.started.connect(trabalhador.rodar)
        trabalhador.concluido.connect(self._analise_concluida)
        trabalhador.erro.connect(self._analise_com_erro)
        trabalhador.concluido.connect(thread.quit)
        trabalhador.erro.connect(thread.quit)
        thread.finished.connect(lambda: self.botao_analisar.setEnabled(True))

        self._thread_analise = thread
        self._trabalhador_analise = trabalhador
        thread.start()

    def _analise_concluida(self, relatorio: dict) -> None:
        self._ultimo_diagnostico = relatorio
        self.area_diagnostico.setPlainText(formatar_diagnostico_para_prompt(relatorio))
        self.rotulo_status.setText(f"Estado estimado: {relatorio['estado_estimado_percentual']}%")

    def _analise_com_erro(self, mensagem: str) -> None:
        self.area_diagnostico.setPlainText(f"Erro ao analisar: {mensagem}")
        self.rotulo_status.setText("Falha na análise — ver acima.")

    # ---- descrever mockup (modelo de visão) ----------------------------------

    def _caminho_configurado(self, chave: str, titulo: str, filtro: str) -> Optional[str]:
        caminho = self._configuracoes.value(chave, "")
        if caminho and Path(caminho).is_file():
            return caminho
        caminho, _ = QFileDialog.getOpenFileName(self, titulo, "", filtro)
        if not caminho:
            return None
        self._configuracoes.setValue(chave, caminho)
        return caminho

    def _gerar_mockup_simples(self) -> None:
        diretorio = Path(tempfile.mkdtemp(prefix="fabrica_local_ia_mockup_"))
        caminho_imagem = diretorio / "mockup_simples.png"
        texto_elementos = self.campo_elementos_mockup.toPlainText().strip()
        elementos = [linha.strip() for linha in texto_elementos.splitlines() if linha.strip()] or None

        gerar_mockup_simples(caminho_imagem, elementos=elementos)

        self._ultimo_mockup_gerado = caminho_imagem
        self.area_log.appendPlainText(f"Mockup simples gerado: {caminho_imagem}")
        self.rotulo_mockup.setText(
            "Mockup simples gerado — clique em \"Descrever mockup…\" para interpretá-lo."
        )

    def _descrever_mockup(self) -> None:
        diretorio_inicial = str(self._ultimo_mockup_gerado.parent) if self._ultimo_mockup_gerado else ""
        imagem, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem do mockup", diretorio_inicial, "Imagens (*.png *.jpg *.jpeg)"
        )
        if not imagem:
            return

        binario = self._caminho_configurado(
            "visao/binario", "Escolher o executável llama-server (com suporte a visão)", "Todos os arquivos (*)"
        )
        if not binario:
            return
        modelo = self._caminho_configurado(
            "visao/modelo", "Escolher o modelo de visão (GGUF)", "Modelos GGUF (*.gguf)"
        )
        if not modelo:
            return
        mmproj = self._caminho_configurado(
            "visao/mmproj", "Escolher o mmproj (projetor multimodal, GGUF)", "Modelos GGUF (*.gguf)"
        )
        if not mmproj:
            return

        self.botao_descrever_mockup.setEnabled(False)
        self.rotulo_mockup.setText("Interpretando mockup — pode levar alguns minutos…")
        self.area_log.appendPlainText(f"Descrevendo mockup: {imagem}")

        thread = QThread(self)
        trabalhador = TrabalhadorDescricaoMockup(Path(binario), Path(modelo), Path(mmproj), Path(imagem))
        trabalhador.moveToThread(thread)
        thread.started.connect(trabalhador.rodar)
        trabalhador.concluido.connect(self._mockup_descrito)
        trabalhador.erro.connect(self._mockup_com_erro)
        trabalhador.concluido.connect(thread.quit)
        trabalhador.erro.connect(thread.quit)
        thread.finished.connect(lambda: self.botao_descrever_mockup.setEnabled(True))

        self._thread_mockup = thread
        self._trabalhador_mockup = trabalhador
        thread.start()

    def _mockup_descrito(self, descricao: str) -> None:
        self._ultima_descricao_mockup = descricao
        self.area_log.appendPlainText(descricao)
        self.rotulo_mockup.setText(f"Descrição de mockup pronta ({len(descricao)} caracteres).")

    def _mockup_com_erro(self, mensagem: str) -> None:
        self.area_log.appendPlainText(f"Erro ao descrever mockup: {mensagem}")
        self.rotulo_mockup.setText("Falha ao descrever mockup — ver log de progresso.")

    def _redefinir_caminhos_visao(self) -> None:
        for chave in ("visao/binario", "visao/modelo", "visao/mmproj"):
            self._configuracoes.remove(chave)
        self.rotulo_mockup.setText(
            "Caminhos do modelo de visão esquecidos — serão pedidos de novo no próximo \"Descrever mockup…\"."
        )

    def _configurar_busca_semantica(self) -> None:
        # Sempre pede de novo (não reaproveita cache como _caminho_configurado)
        # — esse botão é a própria forma de configurar/corrigir, então não
        # tem por que travar num caminho errado escolhido por engano.
        binario, _ = QFileDialog.getOpenFileName(
            self, "Escolher o executável llama-server (para embeddings)", "", "Todos os arquivos (*)"
        )
        if not binario:
            return
        modelo, _ = QFileDialog.getOpenFileName(
            self, "Escolher o modelo de embeddings (GGUF, ex.: CodeRankEmbed)", "", "Modelos GGUF (*.gguf)"
        )
        if not modelo:
            return
        self._configuracoes.setValue("busca/binario", binario)
        self._configuracoes.setValue("busca/modelo", modelo)
        self.rotulo_status.setText(
            "Busca semântica configurada — a ferramenta buscar_codigo fica disponível no próximo \"Executar\"."
        )

    def _aplicar_exemplo_instrucao(self, indice: int) -> None:
        if indice <= 0:
            return
        self.campo_instrucao.setPlainText(EXEMPLOS_INSTRUCAO[indice - 1])
        self.combo_exemplos_instrucao.setCurrentIndex(0)

    # ---- executar orquestrador -----------------------------------------------

    def _executar_orquestrador(self) -> None:
        diretorio = self._diretorio_projeto()
        if diretorio is None:
            return
        instrucao = self.campo_instrucao.toPlainText().strip()
        if not instrucao:
            self.rotulo_status.setText("Escreva uma instrução primeiro.")
            return

        partes_contexto = []
        if self._ultimo_diagnostico:
            partes_contexto.append(formatar_diagnostico_para_prompt(self._ultimo_diagnostico))
        if self._ultima_descricao_mockup:
            partes_contexto.append(self._ultima_descricao_mockup)
        contexto_extra = "\n\n".join(partes_contexto) or None

        self.botao_executar.setEnabled(False)
        self.botao_parar.setEnabled(True)
        self.area_log.clear()
        self._ultima_ferramenta_chamada = None
        if self._ultimo_diagnostico is None:
            self.area_log.appendPlainText(
                "⚠ Sem diagnóstico — o modelo vai chutar a estrutura do projeto. "
                "Considere clicar em \"Analisar projeto\" antes de \"Executar\" da próxima vez.\n"
            )
        self.rotulo_status.setText("Executando…")

        binario_busca = self._configuracoes.value("busca/binario", "")
        modelo_busca = self._configuracoes.value("busca/modelo", "")
        caminho_binario_busca = Path(binario_busca) if binario_busca and Path(binario_busca).is_file() else None
        caminho_modelo_busca = Path(modelo_busca) if modelo_busca and Path(modelo_busca).is_file() else None

        thread = QThread(self)
        trabalhador = TrabalhadorOrquestrador(
            diretorio, instrucao, contexto_extra, caminho_binario_busca, caminho_modelo_busca
        )
        trabalhador.moveToThread(thread)
        thread.started.connect(trabalhador.rodar)
        trabalhador.evento.connect(self.area_log.appendPlainText)
        trabalhador.evento.connect(self._atualizar_painel_codigo)
        trabalhador.evento.connect(self._atualizar_relatorio_erros)
        trabalhador.concluido.connect(self._execucao_concluida)
        trabalhador.erro.connect(self._execucao_com_erro)
        trabalhador.interrompido.connect(self._execucao_interrompida)
        trabalhador.concluido.connect(thread.quit)
        trabalhador.erro.connect(thread.quit)
        trabalhador.interrompido.connect(thread.quit)
        thread.finished.connect(lambda: self.botao_executar.setEnabled(True))
        thread.finished.connect(lambda: self.botao_parar.setEnabled(False))

        self._thread = thread
        self._trabalhador = trabalhador
        thread.start()

    def _parar_orquestrador(self) -> None:
        if self._trabalhador is not None:
            self._trabalhador.solicitar_parada()
        self.botao_parar.setEnabled(False)
        self.rotulo_status.setText("Parando — aguardando a chamada atual terminar…")

    def _execucao_concluida(self, resultado: dict) -> None:
        self.area_log.appendPlainText(f"\nResumo: {resultado.get('resumo', '')}")
        sucesso = resultado.get("sucesso")
        if sucesso is True:
            self.rotulo_status.setText("Concluído com sucesso.")
        elif sucesso is False:
            self.rotulo_status.setText("Concluído sem sucesso — ver resumo/log acima.")
        else:
            self.rotulo_status.setText("Concluído (o modelo respondeu sem chamar finalizar).")

    def _execucao_com_erro(self, mensagem: str) -> None:
        self.area_log.appendPlainText(f"\nErro: {mensagem}")
        self.rotulo_status.setText("Falha na execução — ver log acima.")
        self._registrar_relatorio(f"[execução] {mensagem}")

    def _execucao_interrompida(self) -> None:
        self.area_log.appendPlainText("\nExecução interrompida pelo usuário.")
        self.rotulo_status.setText("Interrompida.")
        self._registrar_relatorio("[execução] interrompida pelo usuário")

    # ---- painel de código e relatório de erros --------------------------------

    def _registrar_relatorio(self, mensagem: str) -> None:
        self.area_relatorios.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {mensagem}")

    def _verificar_configuracao_gpu(self) -> None:
        temperatura = temperatura_gpu_celsius()
        if temperatura is not None:
            self._registrar_relatorio(f"[GPU] Temperatura atual: {temperatura:.0f}°C.")

        processos = listar_processos_llama_server()
        if not processos:
            self._registrar_relatorio("[GPU] Nenhum llama-server rodando no momento.")
            self.rotulo_status.setText("Nenhum llama-server encontrado.")
            return

        sem_limite = [p for p in processos if not p["tem_limite_gpu"]]
        for p in processos:
            porta = f"porta {p['porta']}" if p["porta"] else "porta desconhecida"
            if p["tem_limite_gpu"]:
                self._registrar_relatorio(f"[GPU] PID {p['pid']} ({porta}): OK, rodando com limite de GPU.")
            else:
                self._registrar_relatorio(
                    f"[GPU] ⚠ PID {p['pid']} ({porta}): SEM limite de GPU (-ngl) — risco de sobrecarga."
                )

        if sem_limite:
            self.rotulo_status.setText(
                f"⚠ {len(sem_limite)} llama-server sem limite de GPU — ver painel Relatórios."
            )
        else:
            self.rotulo_status.setText("Todos os llama-server rodando com limite de GPU configurado.")

    def _encerrar_llama_server(self) -> None:
        processos = listar_processos_llama_server()
        if not processos:
            self._registrar_relatorio("[GPU] Nenhum llama-server rodando para encerrar.")
            self.rotulo_status.setText("Nenhum llama-server encontrado.")
            return

        resposta = QMessageBox.question(
            self,
            "Encerrar llama-server",
            f"Encerrar {len(processos)} processo(s) llama-server agora (SIGTERM)? "
            "Isso inclui qualquer servidor de código ou visão subido manualmente — "
            "uma execução em andamento no aplicativo, se houver, vai falhar.",
        )
        if resposta != QMessageBox.Yes:
            return

        encerrados = encerrar_processos_llama_server()
        if encerrados:
            self._registrar_relatorio(f"[GPU] Encerrados: PID(s) {', '.join(str(p) for p in encerrados)}.")
            self.rotulo_status.setText(f"{len(encerrados)} llama-server encerrado(s).")
        else:
            self._registrar_relatorio("[GPU] Nenhum processo foi encerrado (falha ao enviar sinal).")
            self.rotulo_status.setText("Falha ao encerrar llama-server — ver painel Relatórios.")

    def _atualizar_painel_codigo(self, linha: str) -> None:
        prefixo = "escrever_arquivo("
        if not (linha.startswith(prefixo) and linha.endswith(")")):
            return
        try:
            argumentos = json.loads(linha[len(prefixo):-1])
        except json.JSONDecodeError:
            return
        caminho = argumentos.get("caminho", "")
        self.area_codigo.setPlainText(argumentos.get("conteudo", ""))
        self.dock_codigo.setWindowTitle(f"Código — {caminho}" if caminho else "Código")

    def _atualizar_relatorio_erros(self, linha: str) -> None:
        if linha.startswith("erro: "):
            self._registrar_relatorio(f"[{self._ultima_ferramenta_chamada or '?'}] {linha}")
            return

        if linha.startswith("  → "):
            try:
                payload = json.loads(linha[len("  → "):])
            except json.JSONDecodeError:
                return
            if isinstance(payload, dict) and payload.get("codigo_saida") not in (0, None):
                stderr = (payload.get("stderr") or "").strip()[:300]
                self._registrar_relatorio(
                    f"[{self._ultima_ferramenta_chamada or '?'}] código de saída "
                    f"{payload['codigo_saida']}: {stderr}"
                )
            return

        for nome_ferramenta in (
            "ler_arquivo", "escrever_arquivo", "listar_arquivos", "executar_comando", "buscar_codigo", "finalizar",
        ):
            if linha.startswith(nome_ferramenta + "("):
                self._ultima_ferramenta_chamada = nome_ferramenta
                return


def main() -> None:
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
