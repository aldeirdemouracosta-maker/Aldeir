#!/usr/bin/env python3
"""Orquestrador: liga motor_ia + importador_zip + sandbox_execucao num
loop de agente com tool calling sobre um projeto local.

O modelo (via `motor_ia.selecionar_motor`) recebe uma instrução e um
conjunto pequeno de ferramentas (ler/escrever arquivo, rodar comando
em sandbox, finalizar). A cada rodada ele pode chamar uma ferramenta;
o orquestrador executa, devolve o resultado como mensagem "tool" e
repete até o modelo chamar `finalizar` ou o limite de iterações
estourar.

Toda leitura/escrita de arquivo é confinada à raiz do projeto (mesma
defesa contra path traversal usada em importador_zip); todo comando
roda via sandbox_execucao (sem rede, sem escrita fora do projeto,
timeout). O orquestrador nunca executa nada fora dessas duas vias.

Uso:
    python3 orquestrador.py <diretorio_projeto> "<instrucao>"
"""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from motor_ia.selecionar_motor import selecionar_motor
from sandbox_execucao.executar_sandbox import (
    ConfiguracaoSandbox,
    SandboxIndisponivelError,
    executar_comando_sandbox,
)

PROMPT_SISTEMA = """Você é um agente de programação operando sobre um projeto
local. Use as ferramentas disponíveis para ler arquivos antes de
editá-los, faça mudanças mínimas e objetivas, rode comandos para
validar o que fizer, e chame `finalizar` com um resumo assim que a
instrução estiver cumprida ou se não for possível cumpri-la."""

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Lê o conteúdo de um arquivo de texto dentro do projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho relativo à raiz do projeto"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escrever_arquivo",
            "description": "Cria ou sobrescreve um arquivo de texto dentro do projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho relativo à raiz do projeto"},
                    "conteudo": {"type": "string"},
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_comando",
            "description": "Roda um comando isolado (sandbox, sem rede) com a raiz do projeto como diretório de trabalho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Comando e argumentos, ex.: [\"pytest\"]",
                    },
                },
                "required": ["comando"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalizar",
            "description": "Encerra a tarefa e reporta o resultado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo": {"type": "string"},
                    "sucesso": {"type": "boolean"},
                },
                "required": ["resumo", "sucesso"],
            },
        },
    },
]


class MotorIndisponivelError(Exception):
    """Nenhum motor de IA elegível está respondendo (ver motor_ia)."""


class CaminhoForaDoProjetoError(Exception):
    """A ferramenta tentou ler/escrever fora da raiz do projeto."""


class LimiteDeIteracoesError(Exception):
    """O modelo não chamou `finalizar` dentro do número de rodadas permitido."""


class GeracaoTruncadaError(Exception):
    """O modelo atingiu max_tokens sem terminar a resposta — sinal de
    geração descontrolada, não um problema de timeout."""


def _resolver_caminho_seguro(raiz: Path, relativo: str) -> Path:
    raiz = raiz.resolve()
    alvo = (raiz / relativo).resolve()
    if raiz != alvo and raiz not in alvo.parents:
        raise CaminhoForaDoProjetoError(f"caminho fora da raiz do projeto: {relativo!r}")
    return alvo


def ler_arquivo(raiz: Path, relativo: str) -> str:
    caminho = _resolver_caminho_seguro(raiz, relativo)
    return caminho.read_text()


def escrever_arquivo(raiz: Path, relativo: str, conteudo: str) -> None:
    caminho = _resolver_caminho_seguro(raiz, relativo)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo)


def extrair_chamada_de_texto(texto: str) -> Optional[dict]:
    """Fallback para quando o servidor não devolve `tool_calls`
    estruturado, mas o modelo escreveu o JSON da chamada como texto
    solto (visto na prática: llama-server + Qwen2.5-Coder ignoram
    `tool_choice=required` e narram um plano em markdown com blocos
    ```json``` embutidos, em vez de parar numa única chamada).

    Varre `texto` à procura do primeiro objeto JSON top-level com o
    formato `{"name": ..., "arguments": {...}}` e devolve esse dict, ou
    `None` se não encontrar nenhum — sem regex para JSON aninhado
    (frágil); casa chaves manualmente para achar o fim de cada objeto.
    """
    inicio = texto.find("{")
    while inicio != -1:
        profundidade = 0
        for i in range(inicio, len(texto)):
            if texto[i] == "{":
                profundidade += 1
            elif texto[i] == "}":
                profundidade -= 1
                if profundidade == 0:
                    candidato = texto[inicio : i + 1]
                    try:
                        dado = json.loads(candidato)
                    except json.JSONDecodeError:
                        break
                    if isinstance(dado, dict) and "name" in dado and "arguments" in dado:
                        return dado
                    break
        inicio = texto.find("{", inicio + 1)
    return None


def chamar_llm(base_url: str, mensagens: list, timeout: int = 120, max_tokens: int = 512) -> dict:
    # tool_choice="required" pede ao servidor para sempre emitir uma
    # chamada de ferramenta — em motores que respeitam isso, ativa a
    # gramática que garante tool_calls estruturado. Na prática, nem todo
    # motor/modelo obedece (visto com llama-server + Qwen2.5-Coder), por
    # isso o fallback de extrair_chamada_de_texto abaixo é o que garante
    # o funcionamento de verdade, não só esse parâmetro.
    #
    # max_tokens limita o tamanho da resposta: uma chamada de ferramenta
    # válida tem poucas dezenas de tokens, então um valor alto aqui é
    # sinal de geração descontrolada. Cortar cedo transforma isso num
    # erro rápido e observável em vez de um timeout longo e silencioso —
    # mas só levanta erro se nem assim der para extrair uma chamada
    # válida do que já foi gerado (ver abaixo).
    corpo = json.dumps(
        {
            "model": "local",
            "messages": mensagens,
            "tools": FERRAMENTAS,
            "tool_choice": "required",
            "max_tokens": max_tokens,
        }
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
    mensagem = escolha["message"]

    if not mensagem.get("tool_calls"):
        chamada = extrair_chamada_de_texto(mensagem.get("content") or "")
        if chamada is not None:
            mensagem = dict(mensagem)
            mensagem["tool_calls"] = [
                {
                    "id": "extraida_0",
                    "type": "function",
                    "function": {
                        "name": chamada["name"],
                        "arguments": json.dumps(chamada["arguments"]),
                    },
                }
            ]
        elif escolha.get("finish_reason") == "length":
            amostra = (mensagem.get("content") or "")[:800]
            raise GeracaoTruncadaError(
                f"o modelo atingiu o limite de {max_tokens} tokens sem terminar a "
                "resposta, e não foi possível extrair nenhuma chamada de "
                f"ferramenta válida do que foi gerado até o corte:\n{amostra!r}"
            )

    return mensagem


def executar_ferramenta(
    raiz_projeto: Path, config_sandbox: ConfiguracaoSandbox, nome: str, argumentos: dict
) -> str:
    if nome == "ler_arquivo":
        try:
            return ler_arquivo(raiz_projeto, argumentos["caminho"])
        except (OSError, CaminhoForaDoProjetoError) as erro:
            return f"erro: {erro}"

    if nome == "escrever_arquivo":
        try:
            escrever_arquivo(raiz_projeto, argumentos["caminho"], argumentos["conteudo"])
            return "ok"
        except (OSError, CaminhoForaDoProjetoError) as erro:
            return f"erro: {erro}"

    if nome == "executar_comando":
        try:
            resultado = executar_comando_sandbox(
                raiz_projeto, argumentos["comando"], config_sandbox
            )
        except SandboxIndisponivelError as erro:
            return f"erro: {erro}"
        return json.dumps(
            {
                "codigo_saida": resultado.codigo_saida,
                "expirou": resultado.expirou,
                "stdout": resultado.stdout[-4000:],
                "stderr": resultado.stderr[-4000:],
            }
        )

    return f"erro: ferramenta desconhecida {nome!r}"


class Orquestrador:
    def __init__(
        self,
        raiz_projeto: Path,
        config_sandbox: Optional[ConfiguracaoSandbox] = None,
        max_iteracoes: int = 20,
        timeout_llm: int = 300,
        max_tokens_resposta: int = 512,
    ):
        self.raiz_projeto = raiz_projeto
        self.config_sandbox = config_sandbox or ConfiguracaoSandbox()
        self.max_iteracoes = max_iteracoes
        # 300s de padrão: em CPU sem AVX2 + GPU híbrida, processar o prompt
        # inicial (system prompt + ferramentas + diagnóstico) mais a geração
        # com tool_choice=required pode passar de 120s na primeira chamada.
        self.timeout_llm = timeout_llm
        self.max_tokens_resposta = max_tokens_resposta

    def rodar(
        self,
        instrucao: str,
        contexto_extra: Optional[str] = None,
        on_evento: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """`on_evento`, se passado, recebe uma linha de texto a cada
        etapa (útil para mostrar progresso ao vivo numa interface —
        sem isso, `rodar()` só devolve algo quando termina, e uma
        chamada real ao modelo pode levar minutos)."""
        avisar = on_evento or (lambda _: None)

        motor = selecionar_motor()
        if not motor["escolhido"]:
            raise MotorIndisponivelError(motor["mensagem"])
        avisar(f"Motor: {motor['escolhido']} ({motor['base_url']})")

        mensagem_usuario = instrucao if not contexto_extra else f"{contexto_extra}\n\n{instrucao}"
        mensagens = [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": mensagem_usuario},
        ]

        for iteracao in range(self.max_iteracoes):
            avisar(f"Chamando o modelo (tentativa {iteracao + 1}/{self.max_iteracoes})...")
            mensagem_modelo = chamar_llm(
                motor["base_url"],
                mensagens,
                timeout=self.timeout_llm,
                max_tokens=self.max_tokens_resposta,
            )
            mensagens.append(mensagem_modelo)

            chamadas = mensagem_modelo.get("tool_calls") or []
            if not chamadas:
                avisar("Modelo respondeu sem chamar nenhuma ferramenta.")
                return {"resumo": mensagem_modelo.get("content", ""), "sucesso": None}

            for chamada in chamadas:
                nome = chamada["function"]["name"]
                argumentos = json.loads(chamada["function"]["arguments"] or "{}")

                if nome == "finalizar":
                    avisar(f"finalizar(sucesso={argumentos.get('sucesso')})")
                    return argumentos

                avisar(f"{nome}({json.dumps(argumentos, ensure_ascii=False)})")
                resultado = executar_ferramenta(
                    self.raiz_projeto, self.config_sandbox, nome, argumentos
                )
                avisar(f"  → {resultado[:200]}")
                mensagens.append(
                    {
                        "role": "tool",
                        "tool_call_id": chamada["id"],
                        "content": resultado,
                    }
                )

        raise LimiteDeIteracoesError(
            f"{self.max_iteracoes} iterações sem o modelo chamar finalizar"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diretorio_projeto", type=Path)
    parser.add_argument("instrucao")
    parser.add_argument("--timeout-comando", type=int, default=120)
    parser.add_argument(
        "--timeout-llm",
        type=int,
        default=300,
        help="segundos de espera por resposta do modelo (padrão 300; aumente em hardware sem AVX2/GPU híbrida)",
    )
    parser.add_argument(
        "--max-tokens-resposta",
        type=int,
        default=512,
        help="limite de tokens por resposta do modelo (padrão 512; corte cedo em vez de esperar geração descontrolada)",
    )
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="roda analisador_projeto antes e dá o diagnóstico de contexto ao agente",
    )
    parser.add_argument(
        "--contexto-arquivo",
        type=Path,
        default=None,
        help=(
            "arquivo de texto cujo conteúdo é acrescentado como contexto extra "
            "antes da instrução — ex.: a descrição gerada por "
            "`visao_mockup.interpretar_mockup` (motor de visão roda separado, "
            "antes do texto, por causa de VRAM: ver TESTE_LOCAL.md)"
        ),
    )
    args = parser.parse_args()

    partes_contexto = []
    if args.diagnostico:
        from analisador_projeto.analisar_completude import analisar_completude, formatar_diagnostico_para_prompt
        from dataclasses import asdict

        relatorio = asdict(analisar_completude(args.diretorio_projeto))
        partes_contexto.append(formatar_diagnostico_para_prompt(relatorio))
    if args.contexto_arquivo:
        partes_contexto.append(args.contexto_arquivo.read_text())
    contexto_extra = "\n\n".join(partes_contexto) or None

    orquestrador = Orquestrador(
        args.diretorio_projeto,
        ConfiguracaoSandbox(timeout_segundos=args.timeout_comando),
        timeout_llm=args.timeout_llm,
        max_tokens_resposta=args.max_tokens_resposta,
    )
    try:
        resultado = orquestrador.rodar(args.instrucao, contexto_extra=contexto_extra)
    except (MotorIndisponivelError, GeracaoTruncadaError) as erro:
        print(json.dumps({"erro": str(erro)}, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
