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

import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from analisador_projeto.analisar_completude import analisar_completude, formatar_diagnostico_para_prompt
from geracao_mockup.gerar_mockup_simples import gerar_mockup_simples
from importador_zip.inspecionar_zip import analisar_projeto as analisar_zip
from orquestrador.orquestrador import Orquestrador
from visao_mockup.interpretar_mockup import interpretar_mockup as interpretar_mockup_imagem

FONTE_MONO = "Menlo, Consolas, 'DejaVu Sans Mono', monospace"


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

    def __init__(self, diretorio: Path, instrucao: str, contexto_extra: Optional[str]):
        super().__init__()
        self.diretorio = diretorio
        self.instrucao = instrucao
        self.contexto_extra = contexto_extra

    def rodar(self) -> None:
        try:
            orquestrador = Orquestrador(self.diretorio)
            resultado = orquestrador.rodar(
                self.instrucao, contexto_extra=self.contexto_extra, on_evento=self.evento.emit
            )
            self.concluido.emit(resultado)
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

        layout.addWidget(QLabel("Instrução"))
        self.campo_instrucao = QPlainTextEdit()
        self.campo_instrucao.setPlaceholderText("ex.: termine a implementação pendente")
        self.campo_instrucao.setFixedHeight(70)
        layout.addWidget(self.campo_instrucao)

        self.botao_executar = QPushButton("Executar")
        self.botao_executar.clicked.connect(self._executar_orquestrador)
        layout.addWidget(self.botao_executar)

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

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Escolher pasta do projeto")
        if pasta:
            self.campo_pasta.setText(pasta)

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
            self.campo_pasta.setText(destino)
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
            self.campo_pasta.setText(self._destino_zip_pendente)
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
        instrucao = self.campo_instrucao.toPlainText().strip()
        elementos = [linha.strip() for linha in instrucao.splitlines() if linha.strip()] or None

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
        self.area_log.clear()
        self.rotulo_status.setText("Executando…")

        thread = QThread(self)
        trabalhador = TrabalhadorOrquestrador(diretorio, instrucao, contexto_extra)
        trabalhador.moveToThread(thread)
        thread.started.connect(trabalhador.rodar)
        trabalhador.evento.connect(self.area_log.appendPlainText)
        trabalhador.concluido.connect(self._execucao_concluida)
        trabalhador.erro.connect(self._execucao_com_erro)
        trabalhador.concluido.connect(thread.quit)
        trabalhador.erro.connect(thread.quit)
        thread.finished.connect(lambda: self.botao_executar.setEnabled(True))

        self._thread = thread
        self._trabalhador = trabalhador
        thread.start()

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


def main() -> None:
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
