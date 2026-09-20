import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from microagentes.delegar_tarefa import (
    PROMPT_SISTEMA_PADRAO,
    RespostaTruncadaError,
    ServidorMicroagenteIndisponivelError,
    delegar_tarefa,
    gerar_resposta,
    montar_mensagens,
)


def _servidor_com_choice_bruta(choice: dict):
    """Servidor OpenAI-compatible falso que devolve uma `choice` completa
    (não só `message`) — necessário pra testar `finish_reason`, que
    `servidor_llm_mock` (conftest.py) não expõe."""
    porta = None
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            self.rfile.read(tamanho)
            corpo = json.dumps({"choices": [choice]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

    servidor = HTTPServer(("127.0.0.1", porta), _Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor, f"http://127.0.0.1:{porta}/v1"


def test_montar_mensagens_sem_contexto():
    mensagens = montar_mensagens("faça X", None, PROMPT_SISTEMA_PADRAO)
    assert mensagens == [
        {"role": "system", "content": PROMPT_SISTEMA_PADRAO},
        {"role": "user", "content": "faça X"},
    ]


def test_montar_mensagens_com_contexto():
    mensagens = montar_mensagens("faça X", "trecho de código", PROMPT_SISTEMA_PADRAO)
    conteudo = mensagens[1]["content"]
    assert conteudo.startswith("Contexto:\ntrecho de código")
    assert conteudo.endswith("Tarefa:\nfaça X")


def test_gerar_resposta_devolve_conteudo_da_resposta(servidor_llm_mock):
    base_url = servidor_llm_mock([{"role": "assistant", "content": "def cpf_valido(): ..."}])

    resposta = gerar_resposta(base_url, montar_mensagens("gere uma função", None, PROMPT_SISTEMA_PADRAO))

    assert resposta == "def cpf_valido(): ..."


def test_gerar_resposta_levanta_erro_quando_truncada_sem_conteudo():
    # visto na pratica com MiniCPM5-1B: modelo de raciocinio gasta o
    # max_tokens inteiro em reasoning_content e nunca escreve `content`.
    servidor, base_url = _servidor_com_choice_bruta(
        {"finish_reason": "length", "index": 0, "message": {"role": "assistant", "content": ""}}
    )
    try:
        with pytest.raises(RespostaTruncadaError, match="atingiu o limite"):
            gerar_resposta(base_url, montar_mensagens("gere uma função", None, PROMPT_SISTEMA_PADRAO))
    finally:
        servidor.shutdown()


def test_gerar_resposta_nao_levanta_erro_se_truncada_mas_com_conteudo():
    # finish_reason=length mas content nao vazio: geracao cortada, porem
    # ja havia produzido alguma resposta -- nao e o caso que queremos pegar.
    servidor, base_url = _servidor_com_choice_bruta(
        {"finish_reason": "length", "index": 0, "message": {"role": "assistant", "content": "def f(): ..."}}
    )
    try:
        resposta = gerar_resposta(base_url, montar_mensagens("gere uma função", None, PROMPT_SISTEMA_PADRAO))
        assert resposta == "def f(): ..."
    finally:
        servidor.shutdown()


def test_gerar_resposta_conteudo_vazio_sem_finish_reason_length_nao_levanta():
    # content vazio por outro motivo (ex.: finish_reason="stop") nao deve
    # ser tratado como truncamento.
    servidor, base_url = _servidor_com_choice_bruta(
        {"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": ""}}
    )
    try:
        resposta = gerar_resposta(base_url, montar_mensagens("gere uma função", None, PROMPT_SISTEMA_PADRAO))
        assert resposta == ""
    finally:
        servidor.shutdown()


def test_delegar_tarefa_propaga_resposta_truncada_error(tmp_path: Path, monkeypatch):
    import microagentes.delegar_tarefa as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    class _ProcessoFalso2:
        stderr = None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    monkeypatch.setattr(modulo.subprocess, "Popen", lambda comando, **kwargs: _ProcessoFalso2())
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)

    def _gerar_resposta_que_trunca(*a, **k):
        raise RespostaTruncadaError("truncado")

    monkeypatch.setattr(modulo, "gerar_resposta", _gerar_resposta_que_trunca)

    with pytest.raises(RespostaTruncadaError):
        modulo.delegar_tarefa(binario, modelo, "instrução")


def test_delegar_tarefa_falha_alto_quando_binario_nao_existe(tmp_path: Path):
    with pytest.raises(ServidorMicroagenteIndisponivelError, match="binario"):
        delegar_tarefa(tmp_path / "nao-existe", tmp_path / "modelo.gguf", "instrução")


def test_delegar_tarefa_falha_alto_quando_modelo_nao_existe(tmp_path: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)

    with pytest.raises(ServidorMicroagenteIndisponivelError, match="modelo do microagente"):
        delegar_tarefa(binario, tmp_path / "modelo.gguf", "instrução")


class _ProcessoFalso:
    stderr = None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


def test_delegar_tarefa_usa_cpu_por_padrao(tmp_path: Path, monkeypatch):
    # n_gpu_layers=0 por padrao: o coordenador continua rodando na GPU em
    # paralelo (delegar_tarefa nao desliga nada alem do que ele mesmo sobe),
    # entao offload aqui por padrao somaria carga concorrente na GPU.
    import microagentes.delegar_tarefa as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    comandos_capturados = []

    def _popen_falso(comando, **kwargs):
        comandos_capturados.append(comando)
        return _ProcessoFalso()

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_falso)
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "gerar_resposta", lambda *a, **k: "resposta")

    resultado = modulo.delegar_tarefa(binario, modelo, "instrução")

    assert resultado == "resposta"
    comando = comandos_capturados[0]
    assert comando[comando.index("-ngl") + 1] == "0"
    assert comando[comando.index("--ctx-size") + 1] == "4096"


def test_delegar_tarefa_aceita_ngl_customizado(tmp_path: Path, monkeypatch):
    import microagentes.delegar_tarefa as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    comandos_capturados = []

    def _popen_falso(comando, **kwargs):
        comandos_capturados.append(comando)
        return _ProcessoFalso()

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_falso)
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "gerar_resposta", lambda *a, **k: "resposta")
    monkeypatch.setattr(modulo, "temperatura_gpu_celsius", lambda: 40.0)

    modulo.delegar_tarefa(binario, modelo, "instrução", n_gpu_layers=20, ctx_size=2048)

    comando = comandos_capturados[0]
    assert comando[comando.index("-ngl") + 1] == "20"
    assert comando[comando.index("--ctx-size") + 1] == "2048"


def test_delegar_tarefa_recusa_com_gpu_quente(tmp_path: Path, monkeypatch):
    import microagentes.delegar_tarefa as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    monkeypatch.setattr(modulo, "temperatura_gpu_celsius", lambda: 95.0)

    def _popen_que_nao_deveria_ser_chamado(comando, **kwargs):
        raise AssertionError("Popen não deveria ser chamado com GPU quente")

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_que_nao_deveria_ser_chamado)

    with pytest.raises(ServidorMicroagenteIndisponivelError, match="acima do limite seguro"):
        delegar_tarefa(binario, modelo, "instrução", n_gpu_layers=20)


def test_delegar_tarefa_ignora_temperatura_se_ngl_zero(tmp_path: Path, monkeypatch):
    import microagentes.delegar_tarefa as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    monkeypatch.setattr(modulo, "temperatura_gpu_celsius", lambda: 95.0)
    monkeypatch.setattr(modulo.subprocess, "Popen", lambda comando, **kwargs: _ProcessoFalso())
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "gerar_resposta", lambda *a, **k: "resposta")

    assert modulo.delegar_tarefa(binario, modelo, "instrução", n_gpu_layers=0) == "resposta"
