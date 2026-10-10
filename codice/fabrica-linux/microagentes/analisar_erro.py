#!/usr/bin/env python3
"""Delega a análise de um erro (mensagem, stack trace, saída de teste
falhando) a um modelo de raciocínio dedicado — irmão de
`microagentes/delegar_tarefa.py`, mesmo padrão de "agente reduzido",
mas com uma diferença de propósito importante: aqui o modelo *deve*
raciocinar antes de responder, e o raciocínio em si (`reasoning_content`,
quando o servidor expõe esse campo) é aproveitado como parte da análise
— não descartado como em `delegar_tarefa`.

Existe porque um teste real nesta máquina mostrou que modelos de
raciocínio (ex.: MiniCPM5-1B) são ruins pra gerar código rápido (gastam
tokens demais "pensando" antes de responder, e a resposta final às
vezes sai desconectada do raciocínio) — mas raciocinar em várias etapas
é exatamente o que ajuda a diagnosticar a causa de um erro, onde
precisão importa mais que velocidade. Ver TESTE_LOCAL.md, seção 12.

Uso:
    python3 -m microagentes.analisar_erro \
        --binario ./llama.cpp/build/bin/llama-server \
        --modelo ~/modelos/minicpm5-1b/MiniCPM5-1B-Q4_K_M.gguf \
        --erro "pytest: AssertionError em test_soma: esperado 5, recebido 4"
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

from microagentes.delegar_tarefa import RespostaTruncadaError, ServidorMicroagenteIndisponivelError
from motor_ia.selecionar_motor import (
    LIMITE_TEMPERATURA_GPU_CELSIUS,
    endpoint_responde,
    temperatura_gpu_celsius,
)

PROMPT_SISTEMA_ANALISE_ERRO = (
    "Você é um assistente especializado em diagnosticar erros de "
    "programação. Recebeu a descrição de um erro (mensagem, stack "
    "trace, ou saída de teste que falhou) e deve explicar a causa "
    "provável e sugerir uma correção. Pode raciocinar em etapas antes "
    "de concluir — aqui precisão importa mais que velocidade."
)


def montar_mensagens(descricao_erro: str, contexto: Optional[str]) -> list:
    conteudo_usuario = (
        descricao_erro if not contexto else f"Contexto:\n{contexto}\n\nErro a analisar:\n{descricao_erro}"
    )
    return [
        {"role": "system", "content": PROMPT_SISTEMA_ANALISE_ERRO},
        {"role": "user", "content": conteudo_usuario},
    ]


def extrair_analise(mensagem: dict) -> str:
    """Prefere `content` (resposta final), mas cai para `reasoning_content`
    se `content` vier vazio — diferente de `delegar_tarefa.gerar_resposta`,
    aqui o raciocínio tem valor diagnóstico por si só, não é descartável."""
    conteudo = (mensagem.get("content") or "").strip()
    if conteudo:
        return conteudo
    return (mensagem.get("reasoning_content") or "").strip()


def gerar_analise(base_url: str, mensagens: list, timeout: int = 180, max_tokens: int = 2000) -> str:
    """Manda as mensagens para um servidor de análise já rodando e
    devolve o texto da análise. Não gerencia o processo do servidor —
    para isso, veja `analisar_erro`."""
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

    analise = extrair_analise(payload["choices"][0]["message"])
    if not analise:
        raise RespostaTruncadaError(
            f"o modelo atingiu o limite de {max_tokens} tokens sem produzir nenhuma "
            "análise, nem em `content` nem em `reasoning_content`. Aumente max_tokens."
        )
    return analise


def _aguardar_pronto(base_url: str, timeout: float) -> None:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if endpoint_responde(base_url.rstrip("/") + "/models"):
            return
        time.sleep(1)
    raise ServidorMicroagenteIndisponivelError(
        f"o servidor de analise nao respondeu em {base_url} apos {timeout:.0f}s"
    )


def analisar_erro(
    caminho_binario_llama_server: Path,
    caminho_modelo: Path,
    descricao_erro: str,
    contexto: Optional[str] = None,
    porta: int = 8084,
    timeout_subida: float = 60,
    timeout_geracao: int = 180,
    max_tokens: int = 2000,
    n_gpu_layers: int = 0,
    ctx_size: int = 4096,
    limite_temperatura_celsius: Optional[float] = LIMITE_TEMPERATURA_GPU_CELSIUS,
) -> str:
    """Sobe um llama-server com um modelo de raciocínio só para esta
    chamada, manda a descrição do erro, devolve a análise (preferindo
    `content`, caindo para `reasoning_content` se truncado antes da
    resposta final), desliga o servidor no final.

    Porta padrão diferente de `delegar_tarefa` (8084 vs 8083) — os dois
    podem, em tese, ser chamados na mesma execução (analisar um erro e
    depois delegar a correção), então não podem competir pela mesma
    porta.

    `n_gpu_layers=0` (CPU) por padrão, mesmo motivo de `delegar_tarefa`
    (o coordenador continua rodando na GPU em paralelo). `max_tokens=2000`
    — orçamento bem maior que `delegar_tarefa` (1024), de propósito:
    modelos de raciocínio gastam tokens "pensando" antes de responder
    (visto na prática com MiniCPM5-1B, que precisou de 2000 pra terminar
    — ver TESTE_LOCAL.md, seção 12). Mesma checagem de temperatura de
    GPU que os outros agentes reduzidos, se `n_gpu_layers>0`."""
    if not (caminho_binario_llama_server.is_file() and os.access(caminho_binario_llama_server, os.X_OK)):
        raise ServidorMicroagenteIndisponivelError(
            f"binario do llama-server nao encontrado ou sem permissao de execucao: {caminho_binario_llama_server}"
        )
    if not caminho_modelo.is_file():
        raise ServidorMicroagenteIndisponivelError(f"modelo de analise nao encontrado: {caminho_modelo}")

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
                f"servidor de analise nao ficou pronto em {timeout_subida:.0f}s. stderr: {erro[-800:]}"
            ) from None

        mensagens = montar_mensagens(descricao_erro, contexto)
        return gerar_analise(base_url, mensagens, timeout=timeout_geracao, max_tokens=max_tokens)
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
    parser.add_argument("--modelo", type=Path, required=True, help="GGUF do modelo de analise (raciocinio)")
    parser.add_argument("--erro", type=str, required=True, help="Descricao do erro a analisar")
    parser.add_argument("--contexto", type=str, default=None)
    parser.add_argument("--porta", type=int, default=8084)
    parser.add_argument("--timeout-subida", type=float, default=60)
    parser.add_argument("--timeout-geracao", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument(
        "--ngl", type=int, default=0, dest="n_gpu_layers",
        help="camadas offloaded na GPU (padrão 0 = CPU-only, mesmo motivo de delegar_tarefa)",
    )
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument(
        "--sem-checagem-temperatura", action="store_true",
        help="nao recusa subir o servidor mesmo com a GPU quente (sysfs) — use com cautela",
    )
    args = parser.parse_args()

    analise = analisar_erro(
        args.binario,
        args.modelo,
        args.erro,
        contexto=args.contexto,
        porta=args.porta,
        timeout_subida=args.timeout_subida,
        timeout_geracao=args.timeout_geracao,
        max_tokens=args.max_tokens,
        n_gpu_layers=args.n_gpu_layers,
        ctx_size=args.ctx_size,
        limite_temperatura_celsius=None if args.sem_checagem_temperatura else LIMITE_TEMPERATURA_GPU_CELSIUS,
    )
    print(analise)


if __name__ == "__main__":
    main()
