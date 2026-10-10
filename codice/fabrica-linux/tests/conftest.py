"""Fixtures compartilhadas: ZIPs de teste e um servidor OpenAI-compatible
falso para testar orquestrador/orquestrador.py sem depender de um
motor de IA real."""

import json
import socket
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


@pytest.fixture
def zip_legitimo(tmp_path: Path) -> Path:
    caminho = tmp_path / "legitimo.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("main.py", "print('hello')\n")
        zf.writestr("requirements.txt", "requests==2.0\n")
    return caminho


@pytest.fixture
def zip_com_padrao_suspeito(tmp_path: Path) -> Path:
    caminho = tmp_path / "suspeito.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("main.py", "print('hello')\n")
        zf.writestr("malicioso.py", "import os\nos.system('rm -rf /')\n")
    return caminho


@pytest.fixture
def zip_slip(tmp_path: Path) -> Path:
    caminho = tmp_path / "zip_slip.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("arquivo_normal.txt", "ok")
        zf.writestr("../../../../tmp/evil_escaped_teste.txt", "PWNED")
    return caminho


def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


class _HandlerRespostasFixas(BaseHTTPRequestHandler):
    respostas: list = []
    contador = {"n": 0}
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        self.rfile.read(tamanho)

        with self.lock:
            indice = self.contador["n"]
            self.contador["n"] += 1

        mensagem = self.respostas[min(indice, len(self.respostas) - 1)]
        corpo = json.dumps({"choices": [{"message": mensagem}]}).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def servidor_llm_mock():
    """Retorna uma função `subir(respostas) -> base_url` que liga um
    servidor OpenAI-compatible falso devolvendo `respostas` (lista de
    dicts de mensagem `assistant`) em sequência, repetindo a última."""
    servidores = []

    def subir(respostas: list) -> str:
        porta = _porta_livre()
        handler = type(
            "Handler", (_HandlerRespostasFixas,), {"respostas": respostas, "contador": {"n": 0}, "lock": threading.Lock()}
        )
        servidor = HTTPServer(("127.0.0.1", porta), handler)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        servidores.append(servidor)
        return f"http://127.0.0.1:{porta}/v1"

    yield subir

    for servidor in servidores:
        servidor.shutdown()
