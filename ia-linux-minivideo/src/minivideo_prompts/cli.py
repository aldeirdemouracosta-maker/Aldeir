"""minivideo-prompts: assistente de prompts no terminal.

  minivideo-prompts conversar [--modelo ID] [--salvar PASTA_PROJETO]
  minivideo-prompts gerar FICHA.json [--modelo ID]
  minivideo-prompts modelos
"""

from __future__ import annotations

import argparse
import json
import sys

from minivideo_especialistas.llm import ClienteLLM, LLMIndisponivel

from . import modelos
from .conversa import Conversa, salvar


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="minivideo-prompts", description="Assistente de prompts para vídeo.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conversar", help="diálogo no terminal (Ctrl+D encerra)")
    c.add_argument("--modelo", default=modelos.PADRAO, choices=list(modelos.MODELOS))
    c.add_argument("--modo", default="auto", choices=["auto", "regras", "qwen"])
    c.add_argument("--salvar", metavar="PASTA_PROJETO", help="grava o resultado em PASTA_PROJETO/prompts/")
    g = sub.add_parser("gerar", help="gera o prompt a partir de uma ficha JSON")
    g.add_argument("ficha")
    g.add_argument("--modelo", default=modelos.PADRAO, choices=list(modelos.MODELOS))
    sub.add_parser("modelos", help="modelos e formatos suportados")
    a = p.parse_args(argv)

    if a.cmd == "modelos":
        for k, m in modelos.MODELOS.items():
            print(f"{k:<18} {m['nome']} · {m['fps']} fps · {m['tamanho']['landscape']}")
        return 0
    if a.cmd == "gerar":
        with open(a.ficha, encoding="utf-8") as fh:
            ficha = json.load(fh)
        print(json.dumps(modelos.montar(ficha, a.modelo), ensure_ascii=False, indent=2))
        return 0

    try:
        cliente = ClienteLLM()
    except LLMIndisponivel as exc:
        print(f"aviso: {exc}; usando só regras", file=sys.stderr)
        cliente = None
    conv = Conversa(a.modelo, cliente, a.modo)
    print("assistente:", conv.abrir())
    for linha in sys.stdin:
        print("assistente:", conv.responder(linha.rstrip("\n")))
        if conv.pendente is None and conv.obrigatorios_ok() and not linha.startswith("/"):
            break
    doc = conv.resultado()
    print(json.dumps({k: doc[k] for k in ("modelo", "prompt", "prompt_negativo", "parametros")},
                     ensure_ascii=False, indent=2))
    if a.salvar:
        print("salvo:", salvar(doc, a.salvar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
