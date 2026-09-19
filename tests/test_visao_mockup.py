import base64
import json
from pathlib import Path

import pytest

from visao_mockup.interpretar_mockup import (
    ServidorVisaoIndisponivelError,
    codificar_imagem_base64,
    interpretar_imagem,
    interpretar_mockup,
    montar_requisicao,
)


@pytest.fixture
def imagem_fake(tmp_path: Path) -> Path:
    caminho = tmp_path / "mockup.png"
    caminho.write_bytes(b"\x89PNG\r\n\x1a\nconteudo-fake-de-teste")
    return caminho


def test_codificar_imagem_base64_reversivel(imagem_fake: Path):
    codificado = codificar_imagem_base64(imagem_fake)
    assert base64.b64decode(codificado) == imagem_fake.read_bytes()


def test_montar_requisicao_inclui_texto_e_imagem_base64():
    corpo = montar_requisicao("descreva", "QUJD", "image/png", max_tokens=256)

    assert corpo["max_tokens"] == 256
    conteudo = corpo["messages"][0]["content"]
    assert conteudo[0] == {"type": "text", "text": "descreva"}
    assert conteudo[1]["image_url"]["url"] == "data:image/png;base64,QUJD"


def test_interpretar_imagem_devolve_conteudo_da_resposta(servidor_llm_mock, imagem_fake: Path):
    base_url = servidor_llm_mock([{"role": "assistant", "content": "um botao 'Salvar' no rodape"}])

    descricao = interpretar_imagem(base_url, imagem_fake, timeout=5)

    assert descricao == "um botao 'Salvar' no rodape"


def test_interpretar_imagem_manda_prompt_e_imagem_no_corpo(imagem_fake: Path):
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    capturado = {}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            capturado["corpo"] = json.loads(self.rfile.read(tamanho))
            saida = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    try:
        interpretar_imagem(f"http://127.0.0.1:{porta}/v1", imagem_fake, prompt="teste de prompt", timeout=5)
    finally:
        servidor.shutdown()

    conteudo = capturado["corpo"]["messages"][0]["content"]
    assert conteudo[0]["text"] == "teste de prompt"
    assert conteudo[1]["type"] == "image_url"
    assert conteudo[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_interpretar_mockup_falha_alto_quando_binario_nao_existe(tmp_path: Path, imagem_fake: Path):
    with pytest.raises(ServidorVisaoIndisponivelError, match="binario"):
        interpretar_mockup(
            tmp_path / "llama-server-que-nao-existe",
            tmp_path / "modelo.gguf",
            tmp_path / "mmproj.gguf",
            imagem_fake,
        )


def test_interpretar_mockup_falha_alto_quando_modelo_nao_existe(tmp_path: Path, imagem_fake: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)

    with pytest.raises(ServidorVisaoIndisponivelError, match="modelo de visao"):
        interpretar_mockup(binario, tmp_path / "modelo.gguf", tmp_path / "mmproj.gguf", imagem_fake)


def test_interpretar_mockup_falha_alto_quando_imagem_nao_existe(tmp_path: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")
    mmproj = tmp_path / "mmproj.gguf"
    mmproj.write_bytes(b"fake")

    with pytest.raises(ServidorVisaoIndisponivelError, match="imagem"):
        interpretar_mockup(binario, modelo, mmproj, tmp_path / "nao_existe.png")


def test_interpretar_mockup_passa_ngl_e_ctx_size_padrao_conservadores(tmp_path: Path, imagem_fake: Path, monkeypatch):
    import visao_mockup.interpretar_mockup as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")
    mmproj = tmp_path / "mmproj.gguf"
    mmproj.write_bytes(b"fake")

    comandos_capturados = []

    class _ProcessoFalso:
        stderr = None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    def _popen_falso(comando, **kwargs):
        comandos_capturados.append(comando)
        return _ProcessoFalso()

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_falso)
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "interpretar_imagem", lambda *a, **k: "descrição")

    modulo.interpretar_mockup(binario, modelo, mmproj, imagem_fake)

    comando = comandos_capturados[0]
    assert "-ngl" in comando
    assert comando[comando.index("-ngl") + 1] == "20"
    assert "--ctx-size" in comando
    assert comando[comando.index("--ctx-size") + 1] == "4096"


def test_interpretar_mockup_aceita_ngl_e_ctx_size_customizados(tmp_path: Path, imagem_fake: Path, monkeypatch):
    import visao_mockup.interpretar_mockup as modulo

    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")
    mmproj = tmp_path / "mmproj.gguf"
    mmproj.write_bytes(b"fake")

    comandos_capturados = []

    class _ProcessoFalso:
        stderr = None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    def _popen_falso(comando, **kwargs):
        comandos_capturados.append(comando)
        return _ProcessoFalso()

    monkeypatch.setattr(modulo.subprocess, "Popen", _popen_falso)
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)
    monkeypatch.setattr(modulo, "interpretar_imagem", lambda *a, **k: "descrição")

    modulo.interpretar_mockup(binario, modelo, mmproj, imagem_fake, n_gpu_layers=99, ctx_size=8192)

    comando = comandos_capturados[0]
    assert comando[comando.index("-ngl") + 1] == "99"
    assert comando[comando.index("--ctx-size") + 1] == "8192"
