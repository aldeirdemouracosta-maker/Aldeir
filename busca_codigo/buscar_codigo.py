#!/usr/bin/env python3
"""Busca semantica de codigo local via embeddings (CodeRankEmbed + llama.cpp).

Sobe um llama-server temporario com um modelo de embeddings pequeno
(CodeRankEmbed, ~150-300MB em GGUF — nomic-ai/CodeRankEmbed, MIT), indexa
os arquivos de codigo do projeto em pedacos por linha, e devolve os
trechos mais proximos semanticamente de uma pergunta em linguagem
natural — sem o agente precisar ler arquivo por arquivo pra achar o
trecho certo. Mesmo padrao de "agente reduzido, sobe sob demanda e
desliga" usado em visao_mockup/interpretar_mockup.py.

O cache de embeddings fica em <raiz_projeto>/.fabrica_indice_busca.json,
e so reprocessa arquivos que mudaram desde a ultima indexacao (mtime +
tamanho).

Uso:
    python3 -m busca_codigo.buscar_codigo \
        --binario ./llama.cpp/build/bin/llama-server \
        --modelo ~/modelos/coderankembed-q8_0.gguf \
        --projeto ~/meu-projeto \
        --pergunta "onde fica a validacao de login"
"""

import argparse
import json
import math
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from motor_ia.selecionar_motor import endpoint_responde

PREFIXO_QUERY = "Represent this query for searching relevant code: "

EXTENSOES_CODIGO = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".kt", ".swift", ".dart",
}

DIRETORIOS_IGNORADOS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist",
    ".pytest_cache", ".mypy_cache",
}

LINHAS_POR_PEDACO = 60
SOBREPOSICAO_LINHAS = 10

NOME_CACHE = ".fabrica_indice_busca.json"


class ServidorBuscaIndisponivelError(Exception):
    """Levantado quando o binario do llama-server nao existe/nao roda, ou
    o servidor nao fica pronto dentro do timeout."""


@dataclass
class Pedaco:
    arquivo: str
    linha_inicio: int
    linha_fim: int
    texto: str


def _listar_arquivos_codigo(raiz_projeto: Path) -> List[Path]:
    arquivos = []
    for caminho in raiz_projeto.rglob("*"):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_CODIGO:
            continue
        relativo = caminho.relative_to(raiz_projeto)
        if any(parte in DIRETORIOS_IGNORADOS for parte in relativo.parts):
            continue
        arquivos.append(caminho)
    return arquivos


def _dividir_em_pedacos(caminho_relativo: str, texto: str) -> List[Pedaco]:
    linhas = texto.splitlines()
    if not linhas:
        return []
    pedacos = []
    passo = max(1, LINHAS_POR_PEDACO - SOBREPOSICAO_LINHAS)
    inicio = 0
    while True:
        fim = min(inicio + LINHAS_POR_PEDACO, len(linhas))
        trecho = "\n".join(linhas[inicio:fim])
        if trecho.strip():
            pedacos.append(Pedaco(caminho_relativo, inicio + 1, fim, trecho))
        if fim >= len(linhas):
            break
        inicio += passo
    return pedacos


def _assinatura_arquivo(caminho: Path) -> str:
    stat = caminho.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _carregar_cache(raiz_projeto: Path) -> dict:
    caminho_cache = raiz_projeto / NOME_CACHE
    if not caminho_cache.is_file():
        return {}
    try:
        return json.loads(caminho_cache.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _salvar_cache(raiz_projeto: Path, cache: dict) -> None:
    (raiz_projeto / NOME_CACHE).write_text(json.dumps(cache))


def _embutir_textos(base_url: str, textos: List[str], timeout: int = 60) -> List[List[float]]:
    corpo = json.dumps({"input": textos}).encode("utf-8")
    requisicao = urllib.request.Request(
        base_url.rstrip("/") + "/v1/embeddings",
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        payload = json.loads(resposta.read())
    return [item["embedding"] for item in payload["data"]]


def _similaridade_cosseno(a: List[float], b: List[float]) -> float:
    produto = sum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto / (norma_a * norma_b)


def _aguardar_pronto(base_url: str, timeout: float) -> None:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if endpoint_responde(base_url.rstrip("/") + "/models"):
            return
        time.sleep(0.5)
    raise ServidorBuscaIndisponivelError(
        f"o servidor de embeddings nao respondeu em {base_url} apos {timeout:.0f}s"
    )


def indexar_projeto(raiz_projeto: Path, base_url: str) -> dict:
    """Garante que o cache de embeddings esta atualizado — so reprocessa
    (e reembute) arquivos novos ou modificados desde a ultima indexacao,
    reaproveitando os pedacos ja calculados dos que nao mudaram."""
    cache = _carregar_cache(raiz_projeto)
    assinaturas_antigas = cache.get("arquivos", {})
    pedacos_antigos = cache.get("pedacos", [])

    assinaturas_novas = {}
    pedacos_finais = []
    pedacos_a_calcular = []

    for caminho in _listar_arquivos_codigo(raiz_projeto):
        relativo = str(caminho.relative_to(raiz_projeto))
        assinatura = _assinatura_arquivo(caminho)
        assinaturas_novas[relativo] = assinatura

        if assinaturas_antigas.get(relativo) == assinatura:
            pedacos_finais.extend(p for p in pedacos_antigos if p["arquivo"] == relativo)
            continue

        try:
            texto = caminho.read_text(errors="replace")
        except OSError:
            continue
        pedacos_a_calcular.extend(_dividir_em_pedacos(relativo, texto))

    if pedacos_a_calcular:
        embeddings = _embutir_textos(base_url, [p.texto for p in pedacos_a_calcular])
        for pedaco, embedding in zip(pedacos_a_calcular, embeddings):
            pedacos_finais.append({**asdict(pedaco), "embedding": embedding})

    cache_novo = {"arquivos": assinaturas_novas, "pedacos": pedacos_finais}
    _salvar_cache(raiz_projeto, cache_novo)
    return cache_novo


def buscar_codigo(
    caminho_binario_llama_server: Path,
    caminho_modelo: Path,
    raiz_projeto: Path,
    pergunta: str,
    porta: int = 8082,
    top_k: int = 5,
    timeout_subida: float = 30,
) -> List[dict]:
    """Sobe um llama-server com o modelo de embeddings so para esta
    chamada, (re)indexa o projeto sob demanda, busca os pedacos mais
    proximos de `pergunta`, desliga o servidor, e devolve os resultados —
    ordenados por similaridade, mais relevante primeiro."""
    if not (caminho_binario_llama_server.is_file() and os.access(caminho_binario_llama_server, os.X_OK)):
        raise ServidorBuscaIndisponivelError(
            f"binario do llama-server nao encontrado ou sem permissao de execucao: {caminho_binario_llama_server}"
        )
    if not caminho_modelo.is_file():
        raise ServidorBuscaIndisponivelError(f"modelo de embeddings nao encontrado: {caminho_modelo}")
    if not raiz_projeto.is_dir():
        raise ServidorBuscaIndisponivelError(f"pasta do projeto nao encontrada: {raiz_projeto}")

    base_url = f"http://127.0.0.1:{porta}/v1"
    processo = subprocess.Popen(
        [
            str(caminho_binario_llama_server),
            "-m", str(caminho_modelo),
            "--embeddings",
            "--port", str(porta),
            "--host", "127.0.0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            _aguardar_pronto(base_url, timeout_subida)
        except ServidorBuscaIndisponivelError:
            processo.poll()
            erro = processo.stderr.read().decode("utf-8", errors="replace") if processo.stderr else ""
            raise ServidorBuscaIndisponivelError(
                f"servidor de embeddings nao ficou pronto em {timeout_subida:.0f}s. stderr: {erro[-800:]}"
            ) from None

        cache = indexar_projeto(raiz_projeto, base_url)
        pedacos = cache["pedacos"]
        if not pedacos:
            return []

        embedding_pergunta = _embutir_textos(base_url, [PREFIXO_QUERY + pergunta])[0]
        resultados = [
            {
                "arquivo": p["arquivo"],
                "linha_inicio": p["linha_inicio"],
                "linha_fim": p["linha_fim"],
                "trecho": p["texto"],
                "pontuacao": _similaridade_cosseno(embedding_pergunta, p["embedding"]),
            }
            for p in pedacos
        ]
        resultados.sort(key=lambda r: r["pontuacao"], reverse=True)
        return resultados[:top_k]
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binario", type=Path, required=True, help="Caminho do executavel llama-server")
    parser.add_argument("--modelo", type=Path, required=True, help="GGUF do modelo de embeddings")
    parser.add_argument("--projeto", type=Path, required=True, help="Raiz do projeto a indexar/buscar")
    parser.add_argument("--pergunta", type=str, required=True)
    parser.add_argument("--porta", type=int, default=8082)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout-subida", type=float, default=30)
    args = parser.parse_args()

    resultados = buscar_codigo(
        args.binario,
        args.modelo,
        args.projeto,
        args.pergunta,
        porta=args.porta,
        top_k=args.top_k,
        timeout_subida=args.timeout_subida,
    )
    for resultado in resultados:
        print(f"{resultado['arquivo']}:{resultado['linha_inicio']}-{resultado['linha_fim']} "
              f"(pontuacao={resultado['pontuacao']:.3f})")
        print(resultado["trecho"])
        print("---")


if __name__ == "__main__":
    main()
