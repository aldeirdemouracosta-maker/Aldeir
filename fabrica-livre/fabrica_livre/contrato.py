"""Contrato entre o núcleo do agente e a interface de terminal.

Este arquivo é a única coisa que as duas partes compartilham:

  - o NÚCLEO (nucleo.py) implementa `Agente`: conversa com a IA local,
    executa as ferramentas e aplica as proteções (loop, alucinação...);
  - a INTERFACE (interface.py, __main__.py) só consome os `Evento`s que o
    agente produz e responde aos pedidos de aprovação.

Não altere este arquivo sem combinar com a outra parte: qualquer mudança
aqui quebra o lado de lá. Só usa a biblioteca padrão (Python 3.10+).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Literal, Protocol

# --------------------------------------------------------------------- configuração

Modo = Literal["leitura", "manual", "auto"]
"""leitura: só lê arquivos; manual: pede aprovação para alterar/rodar; auto: faz sem perguntar."""


@dataclass
class Config:
    url: str = "http://127.0.0.1:11434/v1"     # servidor compatível com OpenAI (Ollama, LM Studio, proxy)
    modelo: str = "qwen3:8b"
    modo: Modo = "manual"
    max_etapas: int = 30                       # limite de ferramentas por pedido
    sem_pensar: bool = False                   # qwen3: pede resposta sem raciocínio longo


# --------------------------------------------------------------------- eventos

TipoEvento = Literal[
    "inicio",       # dados: {"pedido": str}
    "aguardando",   # dados: {"segundos": float}                      — esperando a IA responder
    "pensando",     # dados: {"texto": str}                           — trecho do raciocínio da IA
    "texto",        # dados: {"texto": str}                           — trecho da resposta (streaming)
    "ferramenta",   # dados: {"nome": str, "argumentos": dict, "descricao": str}
    "resultado",    # dados: {"nome": str, "ok": bool, "saida": str}
    "correcao",     # dados: {"mensagem": str}                        — uma proteção do núcleo agiu
    "erro",         # dados: {"mensagem": str}
    "fim",          # dados: {"ok": bool, "etapas": int, "tokens": int, "segundos": float,
                    #         "arquivos": list[str], "resposta": str}
]


@dataclass
class Evento:
    tipo: TipoEvento
    dados: dict = field(default_factory=dict)
    hora: float = field(default_factory=time.time)


# --------------------------------------------------------------------- aprovação

@dataclass
class Acao:
    """Algo que altera o disco ou roda um comando e, no modo manual, precisa de aprovação."""
    nome: str                 # nome da ferramenta, ex.: "write_file"
    argumentos: dict
    descricao: str            # frase curta para o usuário, ex.: "Escrever calc.py (12 linhas)"
    previa: str = ""          # opcional: diff ou comando completo para mostrar antes de aprovar


Aprovador = Callable[[Acao], bool]
"""A interface fornece esta função; o núcleo a chama antes de cada Acao no modo manual."""


# --------------------------------------------------------------------- agente

class Agente(Protocol):
    def __init__(self, config: Config, pasta: Path, aprovar: Aprovador) -> None: ...

    def executar(self, pedido: str) -> Iterator[Evento]:
        """Processa um pedido do usuário, produzindo eventos até o evento "fim".
        A conversa continua entre chamadas (o agente guarda o histórico)."""
        ...

    def interromper(self) -> None:
        """Pede para parar o pedido em andamento (Ctrl+C na interface). Seguro de chamar de outra thread."""
        ...

    def limpar(self) -> None:
        """Esquece o histórico da conversa."""
        ...

    def modelos(self) -> list[str]:
        """Lista os modelos disponíveis no servidor."""
        ...


# --------------------------------------------------------------------- agente falso (para a interface)

class AgenteFalso:
    """Imita o núcleo com eventos roteirizados, para desenvolver e testar a interface
    sem IA. Use com:  python -m fabrica_livre --falso"""

    def __init__(self, config: Config, pasta: Path, aprovar: Aprovador) -> None:
        self.config, self.pasta, self.aprovar = config, pasta, aprovar
        self._parar = False

    def executar(self, pedido: str) -> Iterator[Evento]:
        self._parar = False
        t0 = time.time()
        yield Evento("inicio", {"pedido": pedido})
        yield Evento("aguardando", {"segundos": 0.0})
        time.sleep(0.6)
        for trecho in ("Vou listar a pasta ", "e criar o arquivo pedido."):
            yield Evento("pensando", {"texto": trecho})
            time.sleep(0.2)
        yield Evento("ferramenta", {"nome": "list_dir", "argumentos": {"path": "."},
                                    "descricao": "Listar a pasta ."})
        yield Evento("resultado", {"nome": "list_dir", "ok": True, "saida": "(pasta vazia)"})
        acao = Acao("write_file", {"path": "ola.py", "content": 'print("ola")\n'},
                    "Escrever ola.py (1 linha)", previa='+ print("ola")')
        aprovado = self.config.modo == "auto" or (self.config.modo == "manual" and self.aprovar(acao))
        if self._parar:
            yield Evento("erro", {"mensagem": "interrompido pelo usuário"})
            yield Evento("fim", {"ok": False, "etapas": 2, "tokens": 120,
                                 "segundos": time.time() - t0, "arquivos": [], "resposta": ""})
            return
        if aprovado:
            yield Evento("ferramenta", {"nome": acao.nome, "argumentos": acao.argumentos,
                                        "descricao": acao.descricao})
            yield Evento("resultado", {"nome": acao.nome, "ok": True, "saida": "ola.py: 1 linha escrita"})
        else:
            yield Evento("correcao", {"mensagem": "Ação recusada: nada foi alterado."})
        resposta = "Pronto: criei ola.py." if aprovado else "Não alterei nada."
        for palavra in resposta.split(" "):
            yield Evento("texto", {"texto": palavra + " "})
            time.sleep(0.05)
        yield Evento("fim", {"ok": True, "etapas": 3, "tokens": 512, "segundos": time.time() - t0,
                             "arquivos": ["ola.py"] if aprovado else [], "resposta": resposta})

    def interromper(self) -> None:
        self._parar = True

    def limpar(self) -> None:
        pass

    def modelos(self) -> list[str]:
        return ["qwen3:8b", "qwen3:4b"]
