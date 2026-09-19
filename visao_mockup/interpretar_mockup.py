#!/usr/bin/env python3
"""Interpreta uma imagem de mockup via modelo de visao local (GGUF + mmproj).

Agente reduzido: nao fica ligado o tempo todo. Sobe um `llama-server`
com um modelo multimodal (Qwen2-VL, LLaVA, ou qualquer GGUF com
`mmproj` compativel), manda a imagem, recebe uma descricao estruturada
dos elementos de interface, e desliga o servidor — pensado para ser
chamado sob demanda pelo orquestrador (ferramenta `interpretar_mockup`)
quando a instrucao do usuario envolver uma imagem, nao para rodar em
paralelo com o modelo de codigo (nao cabem os dois ao mesmo tempo em
8GB de VRAM).

Uso:
    python3 -m visao_mockup.interpretar_mockup \
        --binario ./llama.cpp/build/bin/llama-server \
        --modelo ~/modelos/llava-7b.gguf \
        --mmproj ~/modelos/llava-7b-mmproj.gguf \
        --imagem ~/mockups/tela_principal.png
"""

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from motor_ia.selecionar_motor import endpoint_responde

PROMPT_PADRAO = (
    "Descreva este mockup de interface de aplicativo desktop. Liste cada "
    "elemento visual (botao, campo de texto, lista, card, menu, rotulo) "
    "com seu texto/rotulo e a posicao aproximada (topo/meio/rodape, "
    "esquerda/centro/direita). Seja objetivo, em topicos."
)


class ServidorVisaoIndisponivelError(Exception):
    """Levantado quando o binario do llama-server nao existe/nao roda, ou
    o servidor nao fica pronto dentro do timeout."""


def codificar_imagem_base64(caminho_imagem: Path) -> str:
    return base64.b64encode(caminho_imagem.read_bytes()).decode("ascii")


def _tipo_mime(caminho_imagem: Path) -> str:
    sufixo = caminho_imagem.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(sufixo, "application/octet-stream")


def montar_requisicao(prompt: str, imagem_base64: str, tipo_mime: str, max_tokens: int = 1024) -> dict:
    return {
        "model": "local",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{tipo_mime};base64,{imagem_base64}"}},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }


def interpretar_imagem(
    base_url: str, caminho_imagem: Path, prompt: str = PROMPT_PADRAO, timeout: int = 120, max_tokens: int = 1024
) -> str:
    """Manda a imagem para um servidor de visao ja rodando e devolve a
    descricao gerada. Nao gerencia o processo do servidor — para isso,
    veja `interpretar_mockup`."""
    imagem_base64 = codificar_imagem_base64(caminho_imagem)
    corpo = json.dumps(
        montar_requisicao(prompt, imagem_base64, _tipo_mime(caminho_imagem), max_tokens)
    ).encode("utf-8")

    requisicao = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        payload = json.loads(resposta.read())

    return payload["choices"][0]["message"]["content"] or ""


def _aguardar_pronto(base_url: str, timeout: float) -> None:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if endpoint_responde(base_url.rstrip("/") + "/models"):
            return
        time.sleep(1)
    raise ServidorVisaoIndisponivelError(
        f"o servidor de visao nao respondeu em {base_url} apos {timeout:.0f}s"
    )


def interpretar_mockup(
    caminho_binario_llama_server: Path,
    caminho_modelo: Path,
    caminho_mmproj: Path,
    caminho_imagem: Path,
    porta: int = 8081,
    prompt: str = PROMPT_PADRAO,
    timeout_subida: float = 90,
    timeout_geracao: int = 180,
) -> str:
    """Sobe um llama-server com modelo de visao so para esta chamada,
    interpreta a imagem, desliga o servidor, e devolve a descricao —
    pensado para ser usado por uma unica ferramenta do orquestrador,
    nao para ficar residente."""
    if not (caminho_binario_llama_server.is_file() and os.access(caminho_binario_llama_server, os.X_OK)):
        raise ServidorVisaoIndisponivelError(
            f"binario do llama-server nao encontrado ou sem permissao de execucao: {caminho_binario_llama_server}"
        )
    if not caminho_modelo.is_file():
        raise ServidorVisaoIndisponivelError(f"modelo de visao nao encontrado: {caminho_modelo}")
    if not caminho_mmproj.is_file():
        raise ServidorVisaoIndisponivelError(f"mmproj nao encontrado: {caminho_mmproj}")
    if not caminho_imagem.is_file():
        raise ServidorVisaoIndisponivelError(f"imagem nao encontrada: {caminho_imagem}")

    base_url = f"http://127.0.0.1:{porta}/v1"
    processo = subprocess.Popen(
        [
            str(caminho_binario_llama_server),
            "-m", str(caminho_modelo),
            "--mmproj", str(caminho_mmproj),
            "--port", str(porta),
            "--host", "127.0.0.1",
            "--jinja",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            _aguardar_pronto(base_url, timeout_subida)
        except ServidorVisaoIndisponivelError:
            processo.poll()
            erro = processo.stderr.read().decode("utf-8", errors="replace") if processo.stderr else ""
            raise ServidorVisaoIndisponivelError(
                f"servidor de visao nao ficou pronto em {timeout_subida:.0f}s. stderr: {erro[-800:]}"
            ) from None

        return interpretar_imagem(base_url, caminho_imagem, prompt=prompt, timeout=timeout_geracao)
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
    parser.add_argument("--modelo", type=Path, required=True, help="GGUF do modelo de visao")
    parser.add_argument("--mmproj", type=Path, required=True, help="GGUF do projetor multimodal (mmproj)")
    parser.add_argument("--imagem", type=Path, required=True, help="Imagem do mockup")
    parser.add_argument("--porta", type=int, default=8081)
    parser.add_argument("--prompt", type=str, default=PROMPT_PADRAO)
    parser.add_argument("--timeout-subida", type=float, default=90)
    parser.add_argument("--timeout-geracao", type=int, default=180)
    args = parser.parse_args()

    descricao = interpretar_mockup(
        args.binario,
        args.modelo,
        args.mmproj,
        args.imagem,
        porta=args.porta,
        prompt=args.prompt,
        timeout_subida=args.timeout_subida,
        timeout_geracao=args.timeout_geracao,
    )
    print(descricao)


if __name__ == "__main__":
    main()
