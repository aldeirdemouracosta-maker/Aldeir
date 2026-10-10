import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from microagentes.analisar_erro import (
    PROMPT_SISTEMA_ANALISE_ERRO,
    analisar_erro,
    extrair_analise,
    gerar_analise,
    montar_mensagens,
)
from microagentes.delegar_tarefa import RespostaTruncadaError, ServidorMicroagenteIndisponivelError


def _servidor_com_choice_bruta(choice: dict):
    """Mesmo helper usado em test_microagentes.py: servidor OpenAI-compatible
    falso que devolve uma `choice` completa (não só `message`)."""
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
    mensagens = montar_mensagens("AssertionError em test_soma", None)
    assert mensagens == [
        {"role": "system", "content": PROMPT_SISTEMA_ANALISE_ERRO},
        {"role": "user", "content": "AssertionError em test_soma"},
    ]


def test_montar_mensagens_com_contexto():
    mensagens = montar_mensagens("AssertionError em test_soma", "def soma(a, b): return a")
    conteudo = mensagens[1]["content"]
    assert conteudo.startswith("Contexto:\ndef soma(a, b): return a")
    assert conteudo.endswith("Erro a analisar:\nAssertionError em test_soma")


def test_extrair_analise_prefere_content():
    mensagem = {"content": "resposta final", "reasoning_content": "pensando..."}
    assert extrair_analise(mensagem) == "resposta final"


def test_extrair_analise_cai_para_reasoning_content_se_content_vazio():
    mensagem = {"content": "", "reasoning_content": "o erro é X porque Y"}
    assert extrair_analise(mensagem) == "o erro é X porque Y"


def test_extrair_analise_vazio_se_os_dois_vazios():
    assert extrair_analise({"content": "", "reasoning_content": ""}) == ""
    assert extrair_analise({}) == ""


def test_gerar_analise_usa_content_quando_presente():
    servidor, base_url = _servidor_com_choice_bruta(
        {"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": "causa provável: X"}}
    )
    try:
        analise = gerar_analise(base_url, montar_mensagens("erro", None))
        assert analise == "causa provável: X"
    finally:
        servidor.shutdown()


def test_gerar_analise_usa_reasoning_content_quando_content_vazio():
    servidor, base_url = _servidor_com_choice_bruta(
        {
            "finish_reason": "length",
            "index": 0,
            "message": {"role": "assistant", "content": "", "reasoning_content": "pensando sobre o erro..."},
        }
    )
    try:
        analise = gerar_analise(base_url, montar_mensagens("erro", None))
        assert analise == "pensando sobre o erro..."
    finally:
        servidor.shutdown()


def test_gerar_analise_levanta_erro_se_tudo_vazio():
    servidor, base_url = _servidor_com_choice_bruta(
        {"finish_reason": "length", "index": 0, "message": {"role": "assistant", "content": ""}}
    )
    try:
        with pytest.raises(RespostaTruncadaError, match="atingiu o limite"):
            gerar_analise(base_url, montar_mensagens("erro", None))
    finally:
        servidor.shutdown()


def test_analisar_erro_falha_alto_quando_binario_nao_existe(tmp_path: Path):
    with pytest.raises(ServidorMicroagenteIndisponivelError, match="binario"):
        analisar_erro(tmp_path / "nao-existe", tmp_path / "modelo.gguf", "erro qualquer")


def test_analisar_erro_falha_alto_quando_modelo_nao_existe(tmp_path: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)

    with pytest.raises(ServidorMicroagenteIndisponivelError, match="modelo de analise"):
        analisar_erro(binario, tmp_path / "modelo.gguf", "erro qualquer")


class _ProcessoFalso:
    stderr = None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


def test_analisar_erro_usa_cpu_e_max_tokens_altos_por_padrao(tmp_path: Path, monkeypatch):
    import microagentes.analisar_erro as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    comandos_capturados = []

    def _popen_falso(comando, **kwargs):
        comandos_capturados.append(comando)
        return _ProcessoFalso()

    capturado_max_tokens = {}

    def _gerar_analise_falso(base_url, mensagens, timeout=180, max_tokens=2000):
        capturado_max_tokens["valor"] = max_tokens
        return "análise"

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_falso)
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "gerar_analise", _gerar_analise_falso)

    resultado = modulo.analisar_erro(binario, modelo, "erro qualquer")

    assert resultado == "análise"
    assert capturado_max_tokens["valor"] == 2000
    comando = comandos_capturados[0]
    assert comando[comando.index("-ngl") + 1] == "0"
    assert "8084" in comando  # porta padrão diferente de delegar_tarefa (8083)


def test_analisar_erro_recusa_com_gpu_quente(tmp_path: Path, monkeypatch):
    import microagentes.analisar_erro as modulo

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
        analisar_erro(binario, modelo, "erro qualquer", n_gpu_layers=20)
