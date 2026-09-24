"""CLI ``minivideo-modelos`` — catálogo e organização de modelos (sem downloads)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from minivideo_agents import devices as devmod
from minivideo_agents.workspace import Workspace
from minivideo_especialistas.fiscal import ram_disponivel_mib

from . import gerenciador as g


def cmd_catalogo(args) -> int:
    ws = Workspace(args.workspace)
    presentes = {it.modelo for it in g.inventario(ws.path("Modelos"))}
    for base in ws.models_dirs[1:]:
        if os.path.isdir(base):
            presentes |= {it.modelo for it in g.inventario(base)}
    if args.json:
        print(json.dumps([dict(m, instalado=m["id"] in presentes) for m in g.catalogo()], ensure_ascii=False,
                         indent=2))
        return 0
    print(f"{'modelo':<18} {'agente':<18} {'requer':<18} {'VRAM':>7}  {'estado':<11} licença")
    for m in g.catalogo():
        estado = "instalado" if m["id"] in presentes else ("embutido" if m.get("embutido") else "ausente")
        print(f"{m['id']:<18} {m['agente']:<18} {'/'.join(m['requer']):<18} {m['vram_mib']:>5} M  "
              f"{estado:<11} {m['licenca']}")
    return 0


def cmd_inventario(args) -> int:
    ws = Workspace(args.workspace)
    itens = g.inventario(ws.path("Modelos"))
    if args.json:
        print(json.dumps([i.to_dict() for i in itens], ensure_ascii=False, indent=2))
        return 0
    if not itens:
        print(f"Nenhum modelo em {ws.path('Modelos')}.")
    for it in itens:
        print(f"{it.relativo:<50} {it.tamanho_mib:>9.1f} MiB  {it.formato:<13} {it.modelo or 'desconhecido'}")
        for p in it.problemas:
            print(f"    - {p}")
    return 0


def cmd_organizar(args) -> int:
    ws = Workspace(args.workspace)
    acoes = g.organizar(ws.path("Modelos"), aplicar=args.aplicar)
    if not acoes:
        print("Tudo já está nas pastas padrão.")
    for a in acoes:
        estado = "movido" if a["feito"] else (a["motivo"] or "seria movido (use --aplicar)")
        print(f"{a['de']} -> {a['para']}: {estado}")
    return 0


def cmd_verificar(args) -> int:
    ws = Workspace(args.workspace)
    for r in g.verificar(ws.path("Modelos")):
        origem = "cache" if r["hash_do_cache"] else "calculado"
        print(f"{r['relativo']:<50} {r['sha256'][:16]}… ({origem})")
        for p in r["problemas"]:
            print(f"    - {p}")
    return 0


def cmd_recomendar(args) -> int:
    for r in g.recomendar(devmod.detect(), ram_disponivel_mib()):
        print(f"- {r['id'] or '(indisponível)'} [{r['agente']}]: {r['porque']}"
              + (f"\n    destino: {r['destino']} · licença: {r['licenca']}" if r["id"] else ""))
    print("\nPara instalar: minivideo-modelos instrucoes <modelo>  (nada é baixado automaticamente)")
    return 0


def cmd_instrucoes(args) -> int:
    try:
        print(g.instrucoes(args.modelo))
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


def cmd_baixar(args) -> int:
    from . import baixar as b
    from minivideo_atualizacoes import forjas
    ws = Workspace(args.workspace)
    try:
        cli = forjas.Cliente(timeout=60)
        arq = b.escolher(b._entrada(args.modelo), cli)
    except (b.Recusado, forjas.ErroFonte) as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    tam = f"{arq['tamanho'] / 1048576:.0f} MiB" if arq.get("tamanho") else "tamanho desconhecido"
    print(f"{arq['nome']} ({tam}) · sha256 {arq['sha256'] or 'NÃO publicado'}\n  {arq['url']}")
    if not args.confirmar:
        print("Nada foi baixado. Use --confirmar para baixar.")
        return 0
    try:
        final = b.baixar(ws.path("Modelos"), args.modelo, cli, arquivo=arq, aceitar_sem_hash=args.aceitar_sem_hash)
    except (b.Recusado, forjas.ErroFonte) as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    print(f"Baixado e conferido: {final}")
    return 0


def cmd_calibrar(args) -> int:
    ws = Workspace(args.workspace)
    destino = args.saida or os.path.join(ws.path("Modelos"), "llm", "calibracao.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        r = g.calibrar(args.modelo, args.llama_bench, saida=destino)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Calibração falhou: {exc}", file=sys.stderr)
        return 1
    b = r["melhor"]
    print(f"Melhor: -t {b['threads']} -ngl {b['ngl']} → geração {b['geracao_tok_s']} tok/s, "
          f"prompt {b['prompt_tok_s']} tok/s ({r['segundos']} s). Salvo em {destino}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minivideo-modelos",
                                description="Catálogo, organização, verificação e download (só quando pedido) de modelos.")
    p.add_argument("--workspace")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("catalogo", help="modelos conhecidos, requisitos, licença e se estão instalados")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_catalogo)
    s = sub.add_parser("inventario", help="o que há em Modelos/ (formato pelo cabeçalho do arquivo)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_inventario)
    s = sub.add_parser("organizar", help="move modelos reconhecidos para as pastas padrão")
    s.add_argument("--aplicar", action="store_true", help="sem isso, só mostra o que faria")
    s.set_defaults(func=cmd_organizar)
    sub.add_parser("verificar", help="sha256 de cada modelo (com cache)").set_defaults(func=cmd_verificar)
    sub.add_parser("recomendar", help="modelos que cabem neste hardware").set_defaults(func=cmd_recomendar)
    s = sub.add_parser("instrucoes", help="como obter um modelo manualmente")
    s.add_argument("modelo")
    s.set_defaults(func=cmd_instrucoes)
    s = sub.add_parser("baixar", help="baixa um modelo do Hugging Face com sha256 conferido (pede --confirmar)")
    s.add_argument("modelo")
    s.add_argument("--confirmar", action="store_true", help="sem isso, só mostra o arquivo escolhido")
    s.add_argument("--aceitar-sem-hash", action="store_true")
    s.set_defaults(func=cmd_baixar)
    s = sub.add_parser("calibrar", help="llama-bench: melhores threads e camadas na GPU para um GGUF")
    s.add_argument("modelo")
    s.add_argument("--llama-bench", default="llama-bench")
    s.add_argument("--saida")
    s.set_defaults(func=cmd_calibrar)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
