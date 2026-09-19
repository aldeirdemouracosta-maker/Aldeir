import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from busca_codigo.buscar_codigo import (
    ServidorBuscaIndisponivelError,
    _assinatura_arquivo,
    _dividir_em_pedacos,
    _embutir_textos,
    _listar_arquivos_codigo,
    _similaridade_cosseno,
    buscar_codigo,
    indexar_projeto,
)


def test_dividir_em_pedacos_arquivo_pequeno_vira_um_pedaco_so():
    texto = "\n".join(f"linha {i}" for i in range(10))
    pedacos = _dividir_em_pedacos("app.py", texto)

    assert len(pedacos) == 1
    assert pedacos[0].linha_inicio == 1
    assert pedacos[0].linha_fim == 10


def test_dividir_em_pedacos_arquivo_grande_gera_varios_pedacos_sobrepostos():
    texto = "\n".join(f"linha {i}" for i in range(150))
    pedacos = _dividir_em_pedacos("app.py", texto)

    assert len(pedacos) > 1
    assert pedacos[0].linha_inicio == 1
    assert pedacos[-1].linha_fim == 150
    # sobreposicao: o segundo pedaco comeca antes do primeiro terminar
    assert pedacos[1].linha_inicio < pedacos[0].linha_fim


def test_dividir_em_pedacos_texto_vazio_nao_gera_pedaco():
    assert _dividir_em_pedacos("vazio.py", "") == []


def test_similaridade_cosseno_vetores_identicos_e_um():
    assert _similaridade_cosseno([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_similaridade_cosseno_vetores_ortogonais_e_zero():
    assert _similaridade_cosseno([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_similaridade_cosseno_vetor_nulo_nao_quebra():
    assert _similaridade_cosseno([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_listar_arquivos_codigo_ignora_diretorios_e_extensoes(tmp_path: Path):
    (tmp_path / "app.py").write_text("codigo")
    (tmp_path / "leia.txt").write_text("nao e codigo")
    ignorado = tmp_path / "node_modules"
    ignorado.mkdir()
    (ignorado / "lib.js").write_text("nao deve entrar")
    sub = tmp_path / "pacote"
    sub.mkdir()
    (sub / "modulo.py").write_text("codigo aninhado")

    encontrados = {str(p.relative_to(tmp_path)) for p in _listar_arquivos_codigo(tmp_path)}

    assert encontrados == {"app.py", "pacote/modulo.py"}


def test_assinatura_arquivo_muda_quando_conteudo_muda(tmp_path: Path):
    arquivo = tmp_path / "app.py"
    arquivo.write_text("v1")
    assinatura_1 = _assinatura_arquivo(arquivo)

    arquivo.write_text("versao bem maior que a anterior")
    assinatura_2 = _assinatura_arquivo(arquivo)

    assert assinatura_1 != assinatura_2


@pytest.fixture
def servidor_embeddings_mock():
    """Sobe um servidor HTTP real que responde no formato OpenAI-compatible
    de /v1/embeddings — um vetor determinístico por texto (soma dos
    códigos dos caracteres), suficiente pra testar a lógica de indexação
    e busca sem precisar de um modelo de verdade."""
    servidores = []

    def _vetor_para_texto(texto: str):
        soma = sum(ord(c) for c in texto) % 997
        return [float(soma), float(len(texto)), 1.0]

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho))
            dados = [{"embedding": _vetor_para_texto(texto)} for texto in corpo["input"]]
            saida = json.dumps({"data": dados}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    def subir():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
        s.close()
        servidor = HTTPServer(("127.0.0.1", porta), _Handler)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        servidores.append(servidor)
        return f"http://127.0.0.1:{porta}/v1"

    yield subir

    for servidor in servidores:
        servidor.shutdown()


def test_embutir_textos_manda_lista_e_devolve_embeddings_na_ordem(servidor_embeddings_mock):
    base_url = servidor_embeddings_mock()

    embeddings = _embutir_textos(base_url, ["um", "dois", "tres"])

    assert len(embeddings) == 3
    assert all(isinstance(e, list) for e in embeddings)


def test_indexar_projeto_cria_cache_com_pedacos_de_todos_os_arquivos(tmp_path: Path, servidor_embeddings_mock):
    base_url = servidor_embeddings_mock()
    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n")

    cache = indexar_projeto(tmp_path, base_url)

    assert (tmp_path / ".fabrica_indice_busca.json").is_file()
    arquivos_indexados = {p["arquivo"] for p in cache["pedacos"]}
    assert arquivos_indexados == {"a.py", "b.py"}


def test_indexar_projeto_nao_reprocessa_arquivo_sem_mudanca(tmp_path: Path, servidor_embeddings_mock, monkeypatch):
    import busca_codigo.buscar_codigo as modulo

    base_url = servidor_embeddings_mock()
    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    indexar_projeto(tmp_path, base_url)

    chamadas = {"n": 0}
    original = modulo._embutir_textos

    def _contando(*args, **kwargs):
        chamadas["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(modulo, "_embutir_textos", _contando)

    indexar_projeto(tmp_path, base_url)

    assert chamadas["n"] == 0


def test_indexar_projeto_reprocessa_so_arquivo_modificado(tmp_path: Path, servidor_embeddings_mock, monkeypatch):
    import busca_codigo.buscar_codigo as modulo

    base_url = servidor_embeddings_mock()
    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n")
    indexar_projeto(tmp_path, base_url)

    (tmp_path / "a.py").write_text("def a():\n    return 999\n")

    chamadas = []
    original = modulo._embutir_textos

    def _capturando(base_url, textos, **kwargs):
        chamadas.append(textos)
        return original(base_url, textos, **kwargs)

    monkeypatch.setattr(modulo, "_embutir_textos", _capturando)

    cache = indexar_projeto(tmp_path, base_url)

    assert len(chamadas) == 1
    assert "999" in chamadas[0][0]
    arquivos_indexados = {p["arquivo"] for p in cache["pedacos"]}
    assert arquivos_indexados == {"a.py", "b.py"}


def test_buscar_codigo_ordena_por_similaridade(tmp_path: Path, servidor_embeddings_mock, monkeypatch):
    import busca_codigo.buscar_codigo as modulo

    binario = tmp_path / "llama-server-falso"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "login.py").write_text("def validar_login(usuario, senha):\n    pass\n")
    (projeto / "outro.py").write_text("def formatar_data(d):\n    pass\n")

    base_url = servidor_embeddings_mock()
    porta = int(base_url.rsplit(":", 1)[1].split("/")[0])

    monkeypatch.setattr(modulo.subprocess, "Popen", lambda *a, **k: _ProcessoFalso())
    monkeypatch.setattr(modulo, "_aguardar_pronto", lambda base_url, timeout: None)

    resultados = modulo.buscar_codigo(binario, modelo, projeto, "validar login", porta=porta, top_k=2)

    assert len(resultados) == 2
    assert resultados[0]["pontuacao"] >= resultados[1]["pontuacao"]
    assert {"arquivo", "linha_inicio", "linha_fim", "trecho", "pontuacao"} <= resultados[0].keys()


class _ProcessoFalso:
    stderr = None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


def test_buscar_codigo_falha_alto_quando_binario_nao_existe(tmp_path: Path):
    with pytest.raises(ServidorBuscaIndisponivelError, match="binario"):
        buscar_codigo(tmp_path / "nao-existe", tmp_path / "modelo.gguf", tmp_path, "pergunta")


def test_buscar_codigo_falha_alto_quando_modelo_nao_existe(tmp_path: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)

    with pytest.raises(ServidorBuscaIndisponivelError, match="modelo de embeddings"):
        buscar_codigo(binario, tmp_path / "modelo.gguf", tmp_path, "pergunta")


def test_buscar_codigo_falha_alto_quando_projeto_nao_existe(tmp_path: Path):
    binario = tmp_path / "llama-server"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    modelo = tmp_path / "modelo.gguf"
    modelo.write_bytes(b"fake")

    with pytest.raises(ServidorBuscaIndisponivelError, match="pasta do projeto"):
        buscar_codigo(binario, modelo, tmp_path / "projeto-que-nao-existe", "pergunta")
