"""Testes da interface desktop (PySide6). Rodam sem tela real via
QT_QPA_PLATFORM=offscreen — a variável precisa estar definida antes de
qualquer import do Qt, por isso vem logo no topo do arquivo."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

import interface.janela_principal as jp
import orquestrador.orquestrador as orq
from interface.janela_principal import JanelaPrincipal

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap (bwrap) não instalado neste ambiente — sudo apt install bubblewrap",
)


def _msg_tool_call(id_, nome, argumentos):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}
        ],
    }


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text("def soma(a, b):\n    pass\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _restaurar_selecionar_motor():
    original = orq.selecionar_motor
    yield
    orq.selecionar_motor = original


def test_analisar_projeto_mostra_diagnostico_na_tela(qtbot, projeto: Path):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela.campo_pasta.setText(str(projeto))
    janela.botao_analisar.click()

    qtbot.waitUntil(lambda: janela.botao_analisar.isEnabled(), timeout=5000)

    texto = janela.area_diagnostico.toPlainText()
    assert "função 'soma' sem implementação" in texto
    assert "Estado estimado" in janela.rotulo_status.text()


def test_pasta_inexistente_mostra_erro_sem_travar(qtbot):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela.campo_pasta.setText("/caminho/que/nao/existe/xyz")
    janela.botao_analisar.click()

    assert "não encontrada" in janela.rotulo_status.text()


def test_executar_orquestrador_escreve_arquivo_e_mostra_log(qtbot, projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call(
                "1", "escrever_arquivo", {"caminho": "app.py", "conteudo": "def soma(a, b):\n    return a + b\n"}
            ),
            _msg_tool_call("2", "finalizar", {"resumo": "implementado via UI", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela.campo_pasta.setText(str(projeto))
    janela.campo_instrucao.setPlainText("implemente a função soma")
    janela.botao_executar.click()

    assert janela.botao_executar.isEnabled() is False
    qtbot.waitUntil(lambda: janela.botao_executar.isEnabled(), timeout=5000)

    log = janela.area_log.toPlainText()
    assert "escrever_arquivo" in log
    assert "finalizar(sucesso=True)" in log
    assert janela.rotulo_status.text() == "Concluído com sucesso."
    assert (projeto / "app.py").read_text() == "def soma(a, b):\n    return a + b\n"


def test_executar_sem_instrucao_nao_dispara_nada(qtbot, projeto: Path):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela.campo_pasta.setText(str(projeto))
    janela.botao_executar.click()

    assert janela.botao_executar.isEnabled() is True
    assert "instrução" in janela.rotulo_status.text().lower()


def test_abrir_zip_legitimo_preenche_pasta_automaticamente(qtbot, zip_legitimo: Path):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    from interface.janela_principal import TrabalhadorImportacaoZip

    trabalhador = TrabalhadorImportacaoZip(zip_legitimo)
    resultado = {}
    trabalhador.concluido.connect(lambda r: resultado.update(r))
    trabalhador.rodar()

    qtbot.waitUntil(lambda: bool(resultado), timeout=5000)
    janela._zip_importado(resultado)

    assert resultado["pode_auto_prosseguir"] is True
    assert janela.campo_pasta.text() == resultado["diretorio_extraido"]
    assert Path(janela.campo_pasta.text(), "main.py").is_file()
    assert janela.botao_usar_mesmo_assim.isVisible() is False
    assert "sem riscos detectados" in janela.rotulo_status.text()


def test_abrir_zip_suspeito_exige_confirmacao_antes_de_usar_pasta(qtbot, zip_com_padrao_suspeito: Path):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.show()  # isVisible() só reflete o estado real com a janela exibida

    from interface.janela_principal import TrabalhadorImportacaoZip

    trabalhador = TrabalhadorImportacaoZip(zip_com_padrao_suspeito)
    resultado = {}
    trabalhador.concluido.connect(lambda r: resultado.update(r))
    trabalhador.rodar()

    qtbot.waitUntil(lambda: bool(resultado), timeout=5000)
    janela._zip_importado(resultado)

    assert resultado["pode_auto_prosseguir"] is False
    assert janela.campo_pasta.text() == ""
    assert janela.botao_usar_mesmo_assim.isVisible() is True
    assert "malicioso.py" in janela.area_log.toPlainText()

    janela.botao_usar_mesmo_assim.click()

    assert janela.campo_pasta.text() == resultado["diretorio_extraido"]
    assert janela.botao_usar_mesmo_assim.isVisible() is False


def test_abrir_zip_com_zip_slip_mostra_erro_sem_travar(qtbot, zip_slip: Path):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    from interface.janela_principal import TrabalhadorImportacaoZip

    trabalhador = TrabalhadorImportacaoZip(zip_slip)
    mensagens = []
    trabalhador.erro.connect(mensagens.append)
    trabalhador.rodar()

    qtbot.waitUntil(lambda: bool(mensagens), timeout=5000)
    janela._zip_com_erro(mensagens[0])

    assert "ZipInseguroError" in mensagens[0]
    assert janela.campo_pasta.text() == ""
    assert "Falha ao importar" in janela.rotulo_status.text()


def test_diagnostico_da_tela_e_usado_como_contexto_na_execucao(qtbot, projeto: Path, servidor_llm_mock):
    """Analisar o projeto primeiro deve enriquecer a instrução enviada
    ao modelo com o diagnóstico, igual à flag --diagnostico da CLI."""
    capturado = {}

    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    resposta_finalizar = _msg_tool_call("1", "finalizar", {"resumo": "ok", "sucesso": True})

    class _HandlerCaptura(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho))
            capturado["mensagens"] = corpo["messages"]
            saida = json.dumps({"choices": [{"message": resposta_finalizar}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _HandlerCaptura)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": f"http://127.0.0.1:{porta}/v1"}

    janela = JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.campo_pasta.setText(str(projeto))
    janela.botao_analisar.click()
    qtbot.waitUntil(lambda: janela.botao_analisar.isEnabled(), timeout=5000)

    janela.campo_instrucao.setPlainText("termine a implementação")
    janela.botao_executar.click()
    try:
        qtbot.waitUntil(lambda: janela.botao_executar.isEnabled(), timeout=5000)
    finally:
        servidor.shutdown()

    mensagem_usuario = capturado["mensagens"][1]["content"]
    assert "função 'soma' sem implementação" in mensagem_usuario
    assert mensagem_usuario.endswith("termine a implementação")


def test_paineis_diagnostico_e_progresso_sao_dockwidgets_reposicionaveis(qtbot):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    assert isinstance(janela.dock_diagnostico, QDockWidget)
    assert janela.dock_diagnostico.widget() is janela.area_diagnostico
    assert janela.dock_diagnostico.features() & QDockWidget.DockWidgetMovable
    assert janela.dockWidgetArea(janela.dock_diagnostico) == Qt.RightDockWidgetArea

    assert isinstance(janela.dock_progresso, QDockWidget)
    assert janela.dock_progresso.widget() is janela.area_log
    assert janela.dock_progresso.features() & QDockWidget.DockWidgetMovable
    assert janela.dockWidgetArea(janela.dock_progresso) == Qt.BottomDockWidgetArea


def test_layout_dos_docks_e_salvo_e_restaurado_entre_janelas(qtbot, tmp_path: Path, monkeypatch):
    from PySide6.QtCore import QSettings

    arquivo_config = str(tmp_path / "config.ini")
    monkeypatch.setattr(
        jp, "QSettings", lambda *a, **k: QSettings(arquivo_config, QSettings.IniFormat)
    )

    janela1 = JanelaPrincipal()
    qtbot.addWidget(janela1)
    janela1.dock_diagnostico.setFloating(True)
    janela1.close()

    janela2 = JanelaPrincipal()
    qtbot.addWidget(janela2)

    assert janela2.dock_diagnostico.isFloating() is True


def test_mockup_descrito_atualiza_estado_e_aparece_no_log(qtbot):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela._mockup_descrito("Botão 'Salvar' no rodapé, campo 'Nome' no topo.")

    assert janela._ultima_descricao_mockup == "Botão 'Salvar' no rodapé, campo 'Nome' no topo."
    assert "Botão 'Salvar' no rodapé" in janela.area_log.toPlainText()
    assert "pronta" in janela.rotulo_mockup.text()


def test_erro_ao_descrever_mockup_mostra_mensagem_sem_travar(qtbot):
    janela = JanelaPrincipal()
    qtbot.addWidget(janela)

    janela._mockup_com_erro("ServidorVisaoIndisponivelError: binário não encontrado")

    assert "Falha ao descrever mockup" in janela.rotulo_mockup.text()
    assert "ServidorVisaoIndisponivelError" in janela.area_log.toPlainText()


def test_trabalhador_descricao_mockup_chama_interpretar_e_emite_resultado(qtbot, monkeypatch):
    capturado = {}

    def _interpretar_falso(binario, modelo, mmproj, imagem):
        capturado.update(binario=binario, modelo=modelo, mmproj=mmproj, imagem=imagem)
        return "descrição gerada pelo modelo de visão"

    monkeypatch.setattr(jp, "interpretar_mockup_imagem", _interpretar_falso)

    trabalhador = jp.TrabalhadorDescricaoMockup(
        Path("/bin/llama-server"), Path("/modelos/m.gguf"), Path("/modelos/mmproj.gguf"), Path("/img/mockup.png")
    )
    resultados = []
    trabalhador.concluido.connect(resultados.append)
    trabalhador.rodar()

    assert resultados == ["descrição gerada pelo modelo de visão"]
    assert capturado["binario"] == Path("/bin/llama-server")
    assert capturado["imagem"] == Path("/img/mockup.png")


def test_trabalhador_descricao_mockup_emite_erro_sem_travar(qtbot, monkeypatch):
    def _interpretar_com_falha(binario, modelo, mmproj, imagem):
        raise RuntimeError("servidor de visão não subiu")

    monkeypatch.setattr(jp, "interpretar_mockup_imagem", _interpretar_com_falha)

    trabalhador = jp.TrabalhadorDescricaoMockup(Path("/a"), Path("/b"), Path("/c"), Path("/d"))
    erros = []
    trabalhador.erro.connect(erros.append)
    trabalhador.rodar()

    assert erros == ["RuntimeError: servidor de visão não subiu"]


def test_diagnostico_e_mockup_se_somam_como_contexto_na_execucao(qtbot, projeto: Path, servidor_llm_mock):
    capturado = {}
    resposta_finalizar = _msg_tool_call("1", "finalizar", {"resumo": "ok", "sucesso": True})

    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _HandlerCaptura(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho))
            capturado["mensagens"] = corpo["messages"]
            saida = json.dumps({"choices": [{"message": resposta_finalizar}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _HandlerCaptura)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": f"http://127.0.0.1:{porta}/v1"}

    janela = JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.campo_pasta.setText(str(projeto))
    janela.botao_analisar.click()
    qtbot.waitUntil(lambda: janela.botao_analisar.isEnabled(), timeout=5000)

    janela._mockup_descrito("Mockup: botão 'Salvar' no rodapé, campo 'Nome' no topo.")

    janela.campo_instrucao.setPlainText("implemente a tela do mockup")
    janela.botao_executar.click()
    try:
        qtbot.waitUntil(lambda: janela.botao_executar.isEnabled(), timeout=5000)
    finally:
        servidor.shutdown()

    mensagem_usuario = capturado["mensagens"][1]["content"]
    assert "função 'soma' sem implementação" in mensagem_usuario
    assert "Mockup: botão 'Salvar' no rodapé" in mensagem_usuario
    assert mensagem_usuario.endswith("implemente a tela do mockup")


def test_redefinir_caminhos_visao_limpa_configuracoes_salvas(qtbot, tmp_path: Path, monkeypatch):
    from PySide6.QtCore import QSettings

    arquivo_config = str(tmp_path / "config.ini")
    monkeypatch.setattr(
        jp, "QSettings", lambda *a, **k: QSettings(arquivo_config, QSettings.IniFormat)
    )

    janela = JanelaPrincipal()
    qtbot.addWidget(janela)
    janela._configuracoes.setValue("visao/binario", "/caminho/errado")
    janela._configuracoes.setValue("visao/modelo", "/caminho/errado.gguf")
    janela._configuracoes.setValue("visao/mmproj", "/caminho/errado-mmproj.gguf")

    janela.botao_redefinir_visao.click()

    assert janela._configuracoes.value("visao/binario") is None
    assert janela._configuracoes.value("visao/modelo") is None
    assert janela._configuracoes.value("visao/mmproj") is None
    assert "esquecidos" in janela.rotulo_mockup.text()
