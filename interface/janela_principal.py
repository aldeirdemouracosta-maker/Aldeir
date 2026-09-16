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
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
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
from orquestrador.orquestrador import Orquestrador

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
        self._thread: Optional[QThread] = None
        self._trabalhador: Optional[QObject] = None

        self._montar_widgets()

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
        linha_pasta.addWidget(self.campo_pasta)
        linha_pasta.addWidget(self.botao_procurar)
        layout.addLayout(linha_pasta)

        linha_acoes_diag = QHBoxLayout()
        self.botao_analisar = QPushButton("Analisar projeto")
        self.botao_analisar.clicked.connect(self._analisar_projeto)
        linha_acoes_diag.addWidget(self.botao_analisar)
        linha_acoes_diag.addStretch()
        layout.addLayout(linha_acoes_diag)

        layout.addWidget(QLabel("Diagnóstico"))
        self.area_diagnostico = QPlainTextEdit()
        self.area_diagnostico.setReadOnly(True)
        self.area_diagnostico.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.area_diagnostico.setMaximumBlockCount(2000)
        layout.addWidget(self.area_diagnostico, stretch=1)

        layout.addWidget(QLabel("Instrução"))
        self.campo_instrucao = QPlainTextEdit()
        self.campo_instrucao.setPlaceholderText("ex.: termine a implementação pendente")
        self.campo_instrucao.setFixedHeight(70)
        layout.addWidget(self.campo_instrucao)

        self.botao_executar = QPushButton("Executar")
        self.botao_executar.clicked.connect(self._executar_orquestrador)
        layout.addWidget(self.botao_executar)

        layout.addWidget(QLabel("Progresso"))
        self.area_log = QPlainTextEdit()
        self.area_log.setReadOnly(True)
        self.area_log.setStyleSheet(f"font-family: {FONTE_MONO};")
        self.area_log.setMaximumBlockCount(5000)
        layout.addWidget(self.area_log, stretch=1)

        self.rotulo_status = QLabel("")
        layout.addWidget(self.rotulo_status)

        self.setCentralWidget(centro)

    # ---- pasta do projeto ---------------------------------------------------

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Escolher pasta do projeto")
        if pasta:
            self.campo_pasta.setText(pasta)

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

    # ---- executar orquestrador -----------------------------------------------

    def _executar_orquestrador(self) -> None:
        diretorio = self._diretorio_projeto()
        if diretorio is None:
            return
        instrucao = self.campo_instrucao.toPlainText().strip()
        if not instrucao:
            self.rotulo_status.setText("Escreva uma instrução primeiro.")
            return

        contexto_extra = (
            formatar_diagnostico_para_prompt(self._ultimo_diagnostico) if self._ultimo_diagnostico else None
        )

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
