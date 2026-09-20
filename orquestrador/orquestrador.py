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
instrução estiver cumprida ou se não for possível cumpri-la.

Duas limitações do ambiente que já são esperadas, não bugs a contornar:
- `executar_comando` não tem rede e não mantém estado entre chamadas —
  cada comando roda isolado do zero, então `pip install`, `curl`,
  `git clone` sempre vão falhar, e ativar um venv numa chamada não
  continua valendo na próxima. Não insista tentando de novo: assuma que
  as dependências já estão instaladas e rode o comando final direto
  (ex.: `pytest`, não `source venv/bin/activate && pytest`).
- `escrever_arquivo` sobrescreve o arquivo inteiro. Leia o conteúdo
  atual com `ler_arquivo` antes de editar, e nunca reescreva um arquivo
  inteiro só para corrigir um trecho pequeno — isso apaga tudo que não
  fazia parte do problema."""

# Comandos que dependem de rede — usado por executar_ferramenta para
# reforçar, no próprio resultado da chamada, que vão sempre falhar
# aqui (a sandbox roda com --unshare-net por padrão).
COMANDOS_DE_REDE = ("pip", "pip3", "curl", "wget", "git", "npm", "yarn", "apt", "apt-get", "conda")

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
            "description": (
                "Cria ou sobrescreve um arquivo de texto dentro do projeto. "
                "ATENÇÃO: sobrescreve o arquivo inteiro — leia com ler_arquivo antes "
                "de editar um arquivo existente, e inclua todo o conteúdo que deve "
                "continuar, não só o trecho alterado."
            ),
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
            "name": "listar_arquivos",
            "description": (
                "Lista arquivos e subpastas diretos de uma pasta do projeto (não "
                "recursivo). Use antes de ler_arquivo/buscar_codigo quando não "
                "souber os nomes exatos dos arquivos, ou pra confirmar que um "
                "arquivo/pasta existe antes de tentar acessá-lo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo à raiz do projeto (vazio ou omitido = raiz)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_comando",
            "description": (
                "Roda um comando isolado (sandbox, sem rede) com a raiz do projeto como "
                "diretório de trabalho. Cada chamada é um processo novo: nada persiste "
                "entre chamadas (variáveis de ambiente, `cd`, venv ativado). Sem rede: "
                "não tente `pip install`, `curl` ou `git clone` — sempre vão falhar."
            ),
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

FERRAMENTA_BUSCAR_CODIGO = {
    "type": "function",
    "function": {
        "name": "buscar_codigo",
        "description": (
            "Busca semântica no código do projeto — devolve os trechos mais "
            "relevantes pra uma pergunta em linguagem natural, com arquivo e "
            "linhas, sem precisar ler cada arquivo pra achar o trecho certo. "
            "Use antes de ler_arquivo quando não souber onde procurar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pergunta": {"type": "string", "description": "O que procurar, em linguagem natural"},
            },
            "required": ["pergunta"],
        },
    },
}

FERRAMENTA_DELEGAR_TAREFA = {
    "type": "function",
    "function": {
        "name": "delegar_tarefa",
        "description": (
            "Delega uma sub-tarefa pequena, bem definida e rápida de resolver "
            "(gerar uma função isolada, resumir um trecho) para um modelo "
            "menor e mais rápido, dedicado só a isso — sem acesso a "
            "ferramentas. Use pra tarefas simples e autocontidas em vez de "
            "fazer você mesmo; pra tarefas que exigem ler/escrever arquivos "
            "ou rodar comandos, use as ferramentas normais, não esta; pra "
            "entender a causa de um erro, use analisar_erro, não esta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instrucao": {"type": "string", "description": "A sub-tarefa em linguagem natural"},
                "contexto": {
                    "type": "string",
                    "description": "Contexto opcional (ex.: trecho de código relevante à sub-tarefa)",
                },
            },
            "required": ["instrucao"],
        },
    },
}

FERRAMENTA_ANALISAR_ERRO = {
    "type": "function",
    "function": {
        "name": "analisar_erro",
        "description": (
            "Delega o diagnóstico de um erro (mensagem, stack trace, saída de "
            "teste que falhou) para um modelo especializado em raciocinar "
            "sobre o problema antes de responder — mais lento que "
            "delegar_tarefa, mas mais cuidadoso; use quando precisar entender "
            "a causa de uma falha antes de tentar corrigi-la, não para gerar "
            "código novo (para isso use delegar_tarefa)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "erro": {"type": "string", "description": "A mensagem/stack trace/saída de erro a analisar"},
                "contexto": {
                    "type": "string",
                    "description": "Contexto opcional (ex.: trecho de código relevante ao erro)",
                },
            },
            "required": ["erro"],
        },
    },
}


def montar_ferramentas(
    busca_disponivel: bool, delegacao_disponivel: bool = False, analise_disponivel: bool = False
) -> list:
    """FERRAMENTAS + buscar_codigo/delegar_tarefa/analisar_erro, cada um só
    se o respectivo modelo estiver configurado — não faz sentido anunciar
    ao modelo uma ferramenta que vai sempre falhar por falta de configuração."""
    ferramentas = list(FERRAMENTAS)
    if busca_disponivel:
        ferramentas.append(FERRAMENTA_BUSCAR_CODIGO)
    if delegacao_disponivel:
        ferramentas.append(FERRAMENTA_DELEGAR_TAREFA)
    if analise_disponivel:
        ferramentas.append(FERRAMENTA_ANALISAR_ERRO)
    return ferramentas


class MotorIndisponivelError(Exception):
    """Nenhum motor de IA elegível está respondendo (ver motor_ia)."""


class CaminhoForaDoProjetoError(Exception):
    """A ferramenta tentou ler/escrever fora da raiz do projeto."""


class LimiteDeIteracoesError(Exception):
    """O modelo não chamou `finalizar` dentro do número de rodadas permitido."""


class GeracaoTruncadaError(Exception):
    """O modelo atingiu max_tokens sem terminar a resposta — sinal de
    geração descontrolada, não um problema de timeout."""


class ExecucaoInterrompidaError(Exception):
    """O usuário pediu para parar a execução (via `deve_parar`) antes do
    modelo chamar `finalizar` ou do limite de iterações estourar."""


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


def listar_arquivos(raiz: Path, relativo: str = "") -> list:
    """Lista o conteúdo direto (não recursivo) de uma pasta do projeto —
    alternativa nativa a `executar_comando(["ls", ...])`: não depende do
    sandbox (mais barato, sem subprocesso) e devolve um resultado
    estruturado em vez de texto solto pro modelo interpretar."""
    caminho = _resolver_caminho_seguro(raiz, relativo or ".")
    if not caminho.is_dir():
        raise NotADirectoryError(f"não é uma pasta dentro do projeto: {relativo!r}")
    return [
        {"nome": item.name, "tipo": "pasta" if item.is_dir() else "arquivo"}
        for item in sorted(caminho.iterdir())
    ]


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


def chamar_llm(
    base_url: str, mensagens: list, timeout: int = 120, max_tokens: int = 512, ferramentas: list = None
) -> dict:
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
            "tools": ferramentas if ferramentas is not None else FERRAMENTAS,
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
    raiz_projeto: Path,
    config_sandbox: ConfiguracaoSandbox,
    nome: str,
    argumentos: dict,
    caminho_binario_busca: Optional[Path] = None,
    caminho_modelo_busca: Optional[Path] = None,
    caminho_binario_microagente: Optional[Path] = None,
    caminho_modelo_microagente: Optional[Path] = None,
    caminho_binario_analise: Optional[Path] = None,
    caminho_modelo_analise: Optional[Path] = None,
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

    if nome == "listar_arquivos":
        try:
            itens = listar_arquivos(raiz_projeto, argumentos.get("caminho", ""))
            return json.dumps(itens, ensure_ascii=False)
        except (OSError, CaminhoForaDoProjetoError, NotADirectoryError) as erro:
            return f"erro: {erro}"

    if nome == "executar_comando":
        try:
            resultado = executar_comando_sandbox(
                raiz_projeto, argumentos["comando"], config_sandbox
            )
        except SandboxIndisponivelError as erro:
            return f"erro: {erro}"

        payload = {
            "codigo_saida": resultado.codigo_saida,
            "expirou": resultado.expirou,
            "stdout": resultado.stdout[-4000:],
            "stderr": resultado.stderr[-4000:],
        }
        comando = argumentos.get("comando") or []
        if resultado.codigo_saida not in (0, None) and comando and comando[0] in COMANDOS_DE_REDE:
            # Reforço no próprio resultado da ferramenta, não só no prompt
            # do sistema — visto na prática: um modelo pequeno repetindo
            # `pip install` várias vezes seguidas mesmo com a limitação já
            # documentada no início da conversa. Um aviso bem no ponto em
            # que a falha acontece tem mais chance de ser seguido.
            payload["aviso"] = (
                f"'{comando[0]}' depende de rede, que esta sandbox não tem — isto vai "
                "falhar sempre do mesmo jeito. Não repita este comando; assuma que a "
                "dependência já está instalada ou informe no resumo que ela falta."
            )
        return json.dumps(payload)

    if nome == "buscar_codigo":
        if not (caminho_binario_busca and caminho_modelo_busca):
            return "erro: busca semântica não configurada nesta execução"
        from busca_codigo.buscar_codigo import ServidorBuscaIndisponivelError, buscar_codigo

        try:
            resultados = buscar_codigo(
                caminho_binario_busca, caminho_modelo_busca, raiz_projeto, argumentos["pergunta"]
            )
        except ServidorBuscaIndisponivelError as erro:
            return f"erro: {erro}"
        return json.dumps(resultados, ensure_ascii=False)

    if nome == "delegar_tarefa":
        if not (caminho_binario_microagente and caminho_modelo_microagente):
            return "erro: microagente não configurado nesta execução"
        from microagentes.delegar_tarefa import (
            RespostaTruncadaError,
            ServidorMicroagenteIndisponivelError,
            delegar_tarefa,
        )

        try:
            resposta = delegar_tarefa(
                caminho_binario_microagente,
                caminho_modelo_microagente,
                argumentos["instrucao"],
                contexto=argumentos.get("contexto"),
            )
        except (ServidorMicroagenteIndisponivelError, RespostaTruncadaError) as erro:
            return f"erro: {erro}"
        return resposta

    if nome == "analisar_erro":
        if not (caminho_binario_analise and caminho_modelo_analise):
            return "erro: analisador de erros não configurado nesta execução"
        from microagentes.analisar_erro import analisar_erro
        from microagentes.delegar_tarefa import RespostaTruncadaError, ServidorMicroagenteIndisponivelError

        try:
            analise = analisar_erro(
                caminho_binario_analise,
                caminho_modelo_analise,
                argumentos["erro"],
                contexto=argumentos.get("contexto"),
            )
        except (ServidorMicroagenteIndisponivelError, RespostaTruncadaError) as erro:
            return f"erro: {erro}"
        return analise

    return f"erro: ferramenta desconhecida {nome!r}"


class Orquestrador:
    def __init__(
        self,
        raiz_projeto: Path,
        config_sandbox: Optional[ConfiguracaoSandbox] = None,
        max_iteracoes: int = 20,
        timeout_llm: int = 300,
        max_tokens_resposta: int = 512,
        caminho_binario_busca: Optional[Path] = None,
        caminho_modelo_busca: Optional[Path] = None,
        caminho_binario_microagente: Optional[Path] = None,
        caminho_modelo_microagente: Optional[Path] = None,
        caminho_binario_analise: Optional[Path] = None,
        caminho_modelo_analise: Optional[Path] = None,
    ):
        self.raiz_projeto = raiz_projeto
        self.config_sandbox = config_sandbox or ConfiguracaoSandbox()
        self.max_iteracoes = max_iteracoes
        # 300s de padrão: em CPU sem AVX2 + GPU híbrida, processar o prompt
        # inicial (system prompt + ferramentas + diagnóstico) mais a geração
        # com tool_choice=required pode passar de 120s na primeira chamada.
        self.timeout_llm = timeout_llm
        self.max_tokens_resposta = max_tokens_resposta
        # Opcional: só oferece a ferramenta buscar_codigo se um modelo de
        # embeddings (ex.: CodeRankEmbed) estiver configurado — ver
        # busca_codigo/README.md.
        self.caminho_binario_busca = caminho_binario_busca
        self.caminho_modelo_busca = caminho_modelo_busca
        # Opcional: só oferece a ferramenta delegar_tarefa se um modelo
        # pequeno de microagente (ex.: Qwen2.5-Coder-0.5B) estiver
        # configurado — ver microagentes/README.md.
        self.caminho_binario_microagente = caminho_binario_microagente
        self.caminho_modelo_microagente = caminho_modelo_microagente
        # Opcional: só oferece a ferramenta analisar_erro se um modelo de
        # raciocínio (ex.: MiniCPM5-1B) estiver configurado — separado do
        # microagente de delegação porque o papel exige um modelo diferente
        # (raciocina antes de responder; ver microagentes/analisar_erro.py).
        self.caminho_binario_analise = caminho_binario_analise
        self.caminho_modelo_analise = caminho_modelo_analise

    def rodar(
        self,
        instrucao: str,
        contexto_extra: Optional[str] = None,
        on_evento: Optional[Callable[[str], None]] = None,
        deve_parar: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """`on_evento`, se passado, recebe uma linha de texto a cada
        etapa (útil para mostrar progresso ao vivo numa interface —
        sem isso, `rodar()` só devolve algo quando termina, e uma
        chamada real ao modelo pode levar minutos).

        `deve_parar`, se passado, é checado entre chamadas ao modelo e
        entre ferramentas de uma mesma rodada — se retornar True, a
        execução para com `ExecucaoInterrompidaError` em vez de esperar
        o modelo chamar `finalizar` ou o limite de iterações estourar.
        Não interrompe uma chamada ao modelo ou ferramenta já em
        andamento (isso exigiria cancelamento de rede/subprocesso), só
        evita começar a próxima."""
        avisar = on_evento or (lambda _: None)
        parar_pedido = deve_parar or (lambda: False)

        motor = selecionar_motor()
        if not motor["escolhido"]:
            raise MotorIndisponivelError(motor["mensagem"])
        avisar(f"Motor: {motor['escolhido']} ({motor['base_url']})")

        # Rótulos explícitos, não só concatenação: visto na prática, um
        # modelo pequeno recebendo diagnóstico/descrição de mockup como
        # bloco de texto sem marcação nenhuma pode simplesmente repetir
        # esse contexto de volta como se fosse a resposta, em vez de
        # tratá-lo como referência e agir sobre a instrução de verdade.
        mensagem_usuario = (
            instrucao
            if not contexto_extra
            else (
                f"Contexto de referência (informação de apoio — NÃO é a tarefa a fazer):\n"
                f"{contexto_extra}\n\n"
                f"Tarefa a executar agora:\n{instrucao}"
            )
        )
        mensagens = [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": mensagem_usuario},
        ]
        ferramentas_disponiveis = montar_ferramentas(
            bool(self.caminho_binario_busca and self.caminho_modelo_busca),
            delegacao_disponivel=bool(self.caminho_binario_microagente and self.caminho_modelo_microagente),
            analise_disponivel=bool(self.caminho_binario_analise and self.caminho_modelo_analise),
        )

        for iteracao in range(self.max_iteracoes):
            if parar_pedido():
                avisar("Execução interrompida pelo usuário.")
                raise ExecucaoInterrompidaError("interrompida pelo usuário antes de chamar o modelo")

            avisar(f"Chamando o modelo (tentativa {iteracao + 1}/{self.max_iteracoes})...")
            mensagem_modelo = chamar_llm(
                motor["base_url"],
                mensagens,
                timeout=self.timeout_llm,
                max_tokens=self.max_tokens_resposta,
                ferramentas=ferramentas_disponiveis,
            )
            mensagens.append(mensagem_modelo)

            chamadas = mensagem_modelo.get("tool_calls") or []
            if not chamadas:
                avisar("Modelo respondeu sem chamar nenhuma ferramenta.")
                return {"resumo": mensagem_modelo.get("content", ""), "sucesso": None}

            for chamada in chamadas:
                if parar_pedido():
                    avisar("Execução interrompida pelo usuário.")
                    raise ExecucaoInterrompidaError("interrompida pelo usuário entre chamadas de ferramenta")

                nome = chamada["function"]["name"]
                argumentos = json.loads(chamada["function"]["arguments"] or "{}")

                if nome == "finalizar":
                    avisar(f"finalizar(sucesso={argumentos.get('sucesso')})")
                    return argumentos

                avisar(f"{nome}({json.dumps(argumentos, ensure_ascii=False)})")
                resultado = executar_ferramenta(
                    self.raiz_projeto,
                    self.config_sandbox,
                    nome,
                    argumentos,
                    caminho_binario_busca=self.caminho_binario_busca,
                    caminho_modelo_busca=self.caminho_modelo_busca,
                    caminho_binario_microagente=self.caminho_binario_microagente,
                    caminho_modelo_microagente=self.caminho_modelo_microagente,
                    caminho_binario_analise=self.caminho_binario_analise,
                    caminho_modelo_analise=self.caminho_modelo_analise,
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
    parser.add_argument(
        "--busca-binario",
        type=Path,
        default=None,
        help="executável llama-server pra servir o modelo de embeddings (ativa a ferramenta buscar_codigo)",
    )
    parser.add_argument(
        "--busca-modelo",
        type=Path,
        default=None,
        help="GGUF do modelo de embeddings (ex.: CodeRankEmbed) — ver busca_codigo/README.md",
    )
    parser.add_argument(
        "--microagente-binario",
        type=Path,
        default=None,
        help="executável llama-server pra servir o modelo do microagente (ativa a ferramenta delegar_tarefa)",
    )
    parser.add_argument(
        "--microagente-modelo",
        type=Path,
        default=None,
        help="GGUF de um modelo pequeno pra sub-tarefas (ex.: Qwen2.5-Coder-0.5B) — ver microagentes/README.md",
    )
    parser.add_argument(
        "--analise-binario",
        type=Path,
        default=None,
        help="executável llama-server pra servir o modelo de análise de erros (ativa a ferramenta analisar_erro)",
    )
    parser.add_argument(
        "--analise-modelo",
        type=Path,
        default=None,
        help="GGUF de um modelo de raciocínio pra diagnóstico de erros (ex.: MiniCPM5-1B) — ver microagentes/README.md",
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
        caminho_binario_busca=args.busca_binario,
        caminho_modelo_busca=args.busca_modelo,
        caminho_binario_microagente=args.microagente_binario,
        caminho_modelo_microagente=args.microagente_modelo,
        caminho_binario_analise=args.analise_binario,
        caminho_modelo_analise=args.analise_modelo,
    )
    try:
        resultado = orquestrador.rodar(args.instrucao, contexto_extra=contexto_extra, on_evento=print)
    except (MotorIndisponivelError, GeracaoTruncadaError) as erro:
        print(json.dumps({"erro": str(erro)}, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
