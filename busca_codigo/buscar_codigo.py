#!/usr/bin/env python3
"""Busca semantica + por palavra-chave de codigo local (CodeRankEmbed +
llama.cpp + BM25).

Sobe um llama-server temporario com um modelo de embeddings pequeno
(CodeRankEmbed, ~150-300MB em GGUF — nomic-ai/CodeRankEmbed, MIT), indexa
os arquivos de codigo do projeto em pedacos, e devolve os trechos mais
relevantes pra uma pergunta em linguagem natural — sem o agente precisar
ler arquivo por arquivo pra achar o trecho certo. Mesmo padrao de "agente
reduzido, sobe sob demanda e desliga" usado em
visao_mockup/interpretar_mockup.py.

Pontuacao final combina duas buscas (busca hibrida):
- semantica: similaridade de cosseno entre os embeddings do CodeRankEmbed;
- por palavra-chave: BM25 puro-Python (sem dependencia nova) — ajuda
  muito quando a pergunta cita um nome exato de funcao/variavel, que
  embeddings sozinhos as vezes deixam passar.

Divisao em pedacos: arquivos Python usam o modulo `ast` (ja usado em
analisador_projeto) pra cortar por funcao/classe de nivel superior —
pedacos semanticamente coerentes, nao janelas de linha arbitrarias.
Outras linguagens ainda usam janelas de linha com sobreposicao (chunking
estrutural tipo Tree-sitter pra elas fica pra depois — evita puxar uma
dependencia nativa nova so pra isso agora).

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
import ast
import json
import math
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

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


def _dividir_por_linhas(caminho_relativo: str, texto: str) -> List[Pedaco]:
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


def _dividir_python_por_ast(caminho_relativo: str, texto: str) -> Optional[List[Pedaco]]:
    """Corta um arquivo Python por funcao/classe de nivel superior usando
    `ast` — pedacos coerentes (uma funcao inteira, uma classe inteira) em
    vez de uma janela de linhas arbitraria. Devolve None se o arquivo nao
    parsear (ex.: erro de sintaxe) ou nao tiver nenhuma funcao/classe de
    nivel superior — nesses casos quem chama cai pro chunking por linha."""
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return None

    nos = [n for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    if not nos:
        return None

    linhas = texto.splitlines()
    nos_ordenados = sorted(nos, key=lambda n: n.lineno)
    pedacos = []

    preambulo_fim = nos_ordenados[0].lineno - 1
    if preambulo_fim > 0:
        trecho = "\n".join(linhas[:preambulo_fim]).strip()
        if trecho:
            pedacos.append(Pedaco(caminho_relativo, 1, preambulo_fim, trecho))

    for no in nos_ordenados:
        inicio = no.lineno
        fim = getattr(no, "end_lineno", None) or len(linhas)
        trecho = "\n".join(linhas[inicio - 1 : fim])
        if trecho.strip():
            pedacos.append(Pedaco(caminho_relativo, inicio, fim, trecho))

    return pedacos


def _dividir_arquivo(caminho_relativo: str, texto: str) -> List[Pedaco]:
    if caminho_relativo.endswith(".py"):
        pedacos = _dividir_python_por_ast(caminho_relativo, texto)
        if pedacos is not None:
            return pedacos
    return _dividir_por_linhas(caminho_relativo, texto)


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


BM25_K1 = 1.5
BM25_B = 0.75

_PADRAO_IDENTIFICADOR = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_PADRAO_PARTE_CAMEL_CASE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _tokenizar(texto: str) -> List[str]:
    """Separa identificadores em sub-palavras (snake_case e camelCase) —
    sem isso, `validar_login` vira um token só e nunca bate com uma
    pergunta em linguagem natural como "validar login" (visto na
    prática: BM25 dando pontuação zero pra tudo por causa disso)."""
    tokens = []
    for identificador in _PADRAO_IDENTIFICADOR.findall(texto):
        for parte in identificador.split("_"):
            if not parte:
                continue
            subpartes = _PADRAO_PARTE_CAMEL_CASE.findall(parte) or [parte]
            tokens.extend(sub.lower() for sub in subpartes)
    return tokens


@dataclass
class IndiceBM25:
    frequencias_documento: List[dict]
    frequencia_nos_documentos: dict
    tamanhos: List[int]
    tamanho_medio: float


def _construir_indice_bm25(textos: List[str]) -> IndiceBM25:
    frequencias_documento = []
    frequencia_nos_documentos: dict = {}
    for texto in textos:
        freq: dict = {}
        for token in _tokenizar(texto):
            freq[token] = freq.get(token, 0) + 1
        frequencias_documento.append(freq)
        for token in freq:
            frequencia_nos_documentos[token] = frequencia_nos_documentos.get(token, 0) + 1
    tamanhos = [sum(freq.values()) for freq in frequencias_documento]
    tamanho_medio = sum(tamanhos) / len(tamanhos) if tamanhos else 0.0
    return IndiceBM25(frequencias_documento, frequencia_nos_documentos, tamanhos, tamanho_medio)


def _pontuar_bm25(indice: IndiceBM25, pergunta: str) -> List[float]:
    """BM25 clássico (Robertson-Sparck Jones), implementação direta sem
    dependência nova — o corpus aqui é sempre pequeno (pedaços de um
    projeto local), não precisa de índice invertido otimizado."""
    n_documentos = len(indice.frequencias_documento)
    pontuacoes = [0.0] * n_documentos
    if n_documentos == 0 or indice.tamanho_medio == 0:
        return pontuacoes

    for termo in set(_tokenizar(pergunta)):
        n_t = indice.frequencia_nos_documentos.get(termo, 0)
        if n_t == 0:
            continue
        idf = math.log((n_documentos - n_t + 0.5) / (n_t + 0.5) + 1)
        for i, freq in enumerate(indice.frequencias_documento):
            f = freq.get(termo, 0)
            if f == 0:
                continue
            denominador = f + BM25_K1 * (1 - BM25_B + BM25_B * indice.tamanhos[i] / indice.tamanho_medio)
            pontuacoes[i] += idf * (f * (BM25_K1 + 1)) / denominador
    return pontuacoes


def _normalizar(valores: List[float]) -> List[float]:
    if not valores:
        return []
    minimo, maximo = min(valores), max(valores)
    if maximo == minimo:
        return [0.0 for _ in valores]
    return [(v - minimo) / (maximo - minimo) for v in valores]


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
        pedacos_a_calcular.extend(_dividir_arquivo(relativo, texto))

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
    peso_bm25: float = 0.4,
    n_gpu_layers: int = 0,
    ctx_size: int = 2048,
) -> List[dict]:
    """Sobe um llama-server com o modelo de embeddings so para esta
    chamada, (re)indexa o projeto sob demanda, busca os pedacos mais
    relevantes pra `pergunta` combinando similaridade semantica (embeddings)
    com BM25 (palavra-chave) — `peso_bm25` controla o peso do BM25 na
    combinacao (0 = so semantica, 1 = so palavra-chave; 0.4 por padrao
    porque semantica sozinha as vezes erra nome exato de funcao/variavel).
    Desliga o servidor no final, devolve os resultados ordenados,
    mais relevante primeiro.

    `n_gpu_layers=0` por padrao — o CodeRankEmbed e pequeno o bastante
    pra rodar so em CPU sem ficar lento, e isso soma zero carga extra na
    GPU (que ja esta ocupada com o modelo de codigo/visao). Só suba pra
    GPU se tiver testado que a placa aguenta a carga combinada."""
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
            "-ngl", str(n_gpu_layers),
            "--ctx-size", str(ctx_size),
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
        pontuacoes_semanticas = [_similaridade_cosseno(embedding_pergunta, p["embedding"]) for p in pedacos]

        indice_bm25 = _construir_indice_bm25([p["texto"] for p in pedacos])
        pontuacoes_palavras = _normalizar(_pontuar_bm25(indice_bm25, pergunta))

        resultados = []
        for p, pont_semantica, pont_palavras in zip(pedacos, pontuacoes_semanticas, pontuacoes_palavras):
            resultados.append(
                {
                    "arquivo": p["arquivo"],
                    "linha_inicio": p["linha_inicio"],
                    "linha_fim": p["linha_fim"],
                    "trecho": p["texto"],
                    "pontuacao": (1 - peso_bm25) * pont_semantica + peso_bm25 * pont_palavras,
                    "pontuacao_semantica": pont_semantica,
                    "pontuacao_palavras": pont_palavras,
                }
            )
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
    parser.add_argument(
        "--peso-bm25", type=float, default=0.4, help="0 = só semântica, 1 = só palavra-chave (padrão 0.4)"
    )
    parser.add_argument(
        "--ngl", type=int, default=0, dest="n_gpu_layers",
        help="camadas offloaded na GPU (padrão 0 = só CPU — o modelo de embeddings é pequeno o bastante)",
    )
    parser.add_argument("--ctx-size", type=int, default=2048)
    args = parser.parse_args()

    resultados = buscar_codigo(
        args.binario,
        args.modelo,
        args.projeto,
        args.pergunta,
        porta=args.porta,
        top_k=args.top_k,
        timeout_subida=args.timeout_subida,
        peso_bm25=args.peso_bm25,
        n_gpu_layers=args.n_gpu_layers,
        ctx_size=args.ctx_size,
    )
    for resultado in resultados:
        print(f"{resultado['arquivo']}:{resultado['linha_inicio']}-{resultado['linha_fim']} "
              f"(pontuacao={resultado['pontuacao']:.3f})")
        print(resultado["trecho"])
        print("---")


if __name__ == "__main__":
    main()
