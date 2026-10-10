#!/usr/bin/env python3
"""Delega uma sub-tarefa pequena e bem definida a um modelo dedicado,
menor e mais rápido que o coordenador (agente principal do orquestrador).

Mesmo padrão de "agente reduzido, sobe sob demanda e desliga" usado em
`busca_codigo/buscar_codigo.py` e `visao_mockup/interpretar_mockup.py`:
sobe um `llama-server` só para esta chamada, manda uma única
instrução (sem tool calling — o microagente não tem acesso a
ferramentas, só gera texto/código), devolve a resposta, desliga o
servidor.

Existe porque nem toda sub-tarefa dentro de uma execução precisa do
modelo principal: gerar uma função pequena e isolada, resumir um
trecho, explicar um erro — um modelo de 0,3B-1B (ex.: Qwen2.5-Coder-0.5B,
ver TESTE_LOCAL.md) resolve isso mais rápido e mais leve, deixando o
coordenador livre para decidir o que fazer com o resultado.

Uso:
    python3 -m microagentes.delegar_tarefa \
        --binario ./llama.cpp/build/bin/llama-server \
        --modelo ~/modelos/qwen2.5-coder-0.5b-instruct.gguf \
        --instrucao "escreva uma função que valida um CPF"
"""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from motor_ia.selecionar_motor import (
    LIMITE_TEMPERATURA_GPU_CELSIUS,
    endpoint_responde,
    temperatura_gpu_celsius,
)

PROMPT_SISTEMA_PADRAO = (
    "Você é um assistente auxiliar, executando uma sub-tarefa pequena e "
    "bem definida que outro agente delegou a você. Responda apenas com "
    "o resultado pedido — sem preâmbulo, sem repetir a instrução, sem "
    "chamar ferramentas (você não tem nenhuma disponível)."
)


class ServidorMicroagenteIndisponivelError(Exception):
    """Levantado quando o binario do llama-server nao existe/nao roda, ou
    o servidor nao fica pronto dentro do timeout."""


class RespostaTruncadaError(Exception):
    """Levantado quando o modelo atinge max_tokens sem produzir nenhum
    conteudo em `message.content` — visto na pratica com um modelo de
    raciocinio (MiniCPM5-1B) que gasta o orcamento inteiro de tokens no
    campo separado `reasoning_content` e nunca chega a escrever a
    resposta final. Sem isso, `gerar_resposta` devolveria "" em
    silencio, e quem chamou (o coordenador) nao teria como distinguir
    "resposta vazia de proposito" de "geracao cortada no meio"."""


def montar_mensagens(instrucao: str, contexto: Optional[str], prompt_sistema: str) -> list:
    conteudo_usuario = instrucao if not contexto else f"Contexto:\n{contexto}\n\nTarefa:\n{instrucao}"
    return [
        {"role": "system", "content": prompt_sistema},
        {"role": "user", "content": conteudo_usuario},
    ]


def gerar_resposta(base_url: str, mensagens: list, timeout: int = 120, max_tokens: int = 1024) -> str:
    """Manda as mensagens para um servidor de microagente já rodando e
    devolve o texto gerado. Não gerencia o processo do servidor — para
    isso, veja `delegar_tarefa`."""
    corpo = json.dumps(
        {"model": "local", "messages": mensagens, "max_tokens": max_tokens}
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        payload = json.loads(resposta.read())

    escolha = payload["choices"][0]
    conteudo = escolha["message"].get("content") or ""
    if not conteudo and escolha.get("finish_reason") == "length":
        # Visto na pratica com MiniCPM5-1B: um modelo de raciocinio pode
        # gastar todo o max_tokens em `reasoning_content` (campo separado,
        # fora do que lemos aqui) sem nunca escrever a resposta final em
        # `content`. "" nesse caso nao significa "resposta vazia", significa
        # "geracao cortada antes de comecar a responder de verdade".
        raise RespostaTruncadaError(
            f"o modelo atingiu o limite de {max_tokens} tokens sem produzir nenhuma "
            "resposta em `content` — comum em modelos de raciocínio que gastam o "
            "orçamento pensando antes de responder. Aumente max_tokens ou troque de modelo."
        )
    return conteudo


def _aguardar_pronto(base_url: str, timeout: float) -> None:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if endpoint_responde(base_url.rstrip("/") + "/models"):
            return
        time.sleep(1)
    raise ServidorMicroagenteIndisponivelError(
        f"o servidor do microagente nao respondeu em {base_url} apos {timeout:.0f}s"
    )


def delegar_tarefa(
    caminho_binario_llama_server: Path,
    caminho_modelo: Path,
    instrucao: str,
    contexto: Optional[str] = None,
    prompt_sistema: str = PROMPT_SISTEMA_PADRAO,
    porta: int = 8083,
    timeout_subida: float = 60,
    timeout_geracao: int = 120,
    max_tokens: int = 1024,
    n_gpu_layers: int = 0,
    ctx_size: int = 4096,
    limite_temperatura_celsius: Optional[float] = LIMITE_TEMPERATURA_GPU_CELSIUS,
) -> str:
    """Sobe um llama-server com um modelo pequeno só para esta chamada,
    manda a instrução (sem tool calling), devolve a resposta gerada,
    desliga o servidor no final.

    `n_gpu_layers=0` por padrão (CPU-only) — diferente de
    `interpretar_mockup`/`buscar_codigo` com GPU ligada por padrão:
    aqui o microagente roda **ao mesmo tempo** que o servidor do
    coordenador (que continua de pé, o `delegar_tarefa` não desliga
    nada além do que ele mesmo sobe), então offload na GPU aqui soma
    carga concorrente, não sequencial. Um modelo de 0,3B–1B é leve o
    bastante pra rodar em CPU sem ficar impraticável. Suba pra GPU
    (`n_gpu_layers>0`) só depois de confirmar que o hardware está
    estável sob carga de um único modelo — visto na prática: o
    incidente que motivou toda essa checagem de temperatura aconteceu
    com um único modelo na GPU, então dois ao mesmo tempo é carga
    ainda maior. Mesmo assim, se `n_gpu_layers>0`, confere a
    temperatura da GPU (sysfs) antes de subir o servidor e recusa se
    estiver acima de `limite_temperatura_celsius`, mesma lógica de
    `buscar_codigo`/`interpretar_mockup`. Ver TESTE_LOCAL.md."""
    if not (caminho_binario_llama_server.is_file() and os.access(caminho_binario_llama_server, os.X_OK)):
        raise ServidorMicroagenteIndisponivelError(
            f"binario do llama-server nao encontrado ou sem permissao de execucao: {caminho_binario_llama_server}"
        )
    if not caminho_modelo.is_file():
        raise ServidorMicroagenteIndisponivelError(f"modelo do microagente nao encontrado: {caminho_modelo}")

    if n_gpu_layers > 0 and limite_temperatura_celsius is not None:
        temperatura = temperatura_gpu_celsius()
        if temperatura is not None and temperatura >= limite_temperatura_celsius:
            raise ServidorMicroagenteIndisponivelError(
                f"GPU a {temperatura:.0f}°C, acima do limite seguro "
                f"({limite_temperatura_celsius:.0f}°C) — nao vou subir o llama-server "
                "na GPU agora. Deixe esfriar (ou rode com n_gpu_layers=0) antes de tentar de novo."
            )

    base_url = f"http://127.0.0.1:{porta}/v1"
    processo = subprocess.Popen(
        [
            str(caminho_binario_llama_server),
            "-m", str(caminho_modelo),
            "--port", str(porta),
            "--host", "127.0.0.1",
            "--jinja",
            "-ngl", str(n_gpu_layers),
            "--ctx-size", str(ctx_size),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            _aguardar_pronto(base_url, timeout_subida)
        except ServidorMicroagenteIndisponivelError:
            processo.poll()
            erro = processo.stderr.read().decode("utf-8", errors="replace") if processo.stderr else ""
            raise ServidorMicroagenteIndisponivelError(
                f"servidor do microagente nao ficou pronto em {timeout_subida:.0f}s. stderr: {erro[-800:]}"
            ) from None

        mensagens = montar_mensagens(instrucao, contexto, prompt_sistema)
        return gerar_resposta(base_url, mensagens, timeout=timeout_geracao, max_tokens=max_tokens)
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
    parser.add_argument("--modelo", type=Path, required=True, help="GGUF do modelo do microagente")
    parser.add_argument("--instrucao", type=str, required=True)
    parser.add_argument("--contexto", type=str, default=None)
    parser.add_argument("--porta", type=int, default=8083)
    parser.add_argument("--timeout-subida", type=float, default=60)
    parser.add_argument("--timeout-geracao", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument(
        "--ngl", type=int, default=0, dest="n_gpu_layers",
        help=(
            "camadas offloaded na GPU (padrão 0 = CPU-only — o coordenador continua "
            "rodando na GPU em paralelo, então offload aqui soma carga concorrente)"
        ),
    )
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument(
        "--sem-checagem-temperatura", action="store_true",
        help="nao recusa subir o servidor mesmo com a GPU quente (sysfs) — use com cautela",
    )
    args = parser.parse_args()

    resposta = delegar_tarefa(
        args.binario,
        args.modelo,
        args.instrucao,
        contexto=args.contexto,
        porta=args.porta,
        timeout_subida=args.timeout_subida,
        timeout_geracao=args.timeout_geracao,
        max_tokens=args.max_tokens,
        n_gpu_layers=args.n_gpu_layers,
        ctx_size=args.ctx_size,
        limite_temperatura_celsius=None if args.sem_checagem_temperatura else LIMITE_TEMPERATURA_GPU_CELSIUS,
    )
    print(resposta)


if __name__ == "__main__":
    main()
