"""minivideo-atualizar: índice, instalação atômica e reversão de ferramentas.

  minivideo-atualizar verificar          consulta as fontes e grava o índice (só leitura)
  minivideo-atualizar listar             mostra o índice salvo (sem rede)
  minivideo-atualizar aplicar ID [--aceitar-sem-hash]
  minivideo-atualizar reverter ID
  minivideo-atualizar historico
  minivideo-atualizar caminhos           pastas que entram na frente do PATH
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List

from minivideo_agents.workspace import Workspace

from . import forjas, indice, instalador

MARCA = {True: "[novo]", False: "[ok]  "}


def linhas_indice(doc: Dict) -> List[str]:
    out = [f"Consultado em {doc['consultado_em']}"]
    for it in doc["itens"]:
        if it.get("erro") and not it.get("disponivel"):
            out.append(f"[erro] {it['id']:<24} {it['forja']}:{it['repo']} — {it['erro']}")
            continue
        seta = f"{it['instalada'] or '?'} -> {it['disponivel']}" if it["novo"] else (it["instalada"] or it["disponivel"])
        extra = ""
        if it.get("arquivo"):
            extra = " · sha256 publicado" if it["arquivo"].get("sha256") else " · SEM sha256 publicado"
        if it.get("erro"):
            extra += f" · {it['erro']}"
        out.append(f"{MARCA[bool(it['novo'])]} {it['id']:<24} {seta:<24} {it['tipo']:<10} {it['forja']}{extra}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="minivideo-atualizar", description=__doc__.split("\n")[0])
    p.add_argument("--workspace")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verificar")
    sub.add_parser("listar")
    a = sub.add_parser("aplicar")
    a.add_argument("id")
    a.add_argument("--aceitar-sem-hash", action="store_true")
    r = sub.add_parser("reverter")
    r.add_argument("id")
    sub.add_parser("historico")
    sub.add_parser("caminhos")
    args = p.parse_args(argv)
    ws = Workspace(args.workspace)

    if args.cmd == "verificar":
        print("\n".join(linhas_indice(indice.atualizar_indice(ws.root))))
    elif args.cmd == "listar":
        doc = indice.ler_indice(ws.root)
        if not doc:
            print("sem índice: rode 'minivideo-atualizar verificar'")
            return 1
        print("\n".join(linhas_indice(doc)))
    elif args.cmd == "aplicar":
        doc = indice.ler_indice(ws.root) or {"itens": []}
        linha = next((i for i in doc["itens"] if i["id"] == args.id), None)
        item = next((i for i in indice.carregar_fontes(ws.root) if i["id"] == args.id), None)
        if not item or not linha:
            print(f"{args.id}: não está no índice; rode 'verificar' antes", file=sys.stderr)
            return 1
        try:
            v = instalador.aplicar(ws.root, item, linha, aceitar_sem_hash=args.aceitar_sem_hash)
        except (instalador.Recusado, forjas.ErroFonte) as exc:
            print(f"recusado: {exc}", file=sys.stderr)
            return 2
        if item["tipo"] == "sistema":
            print(f"ISO conferido em {v}\nGrave num pendrive: sudo dd if={v} of=/dev/sdX bs=4M conv=fsync "
                  "(confira /dev/sdX com lsblk; APAGA o pendrive)")
        else:
            print(f"{args.id} {v} ativo (reverter: minivideo-atualizar reverter {args.id})")
    elif args.cmd == "reverter":
        try:
            print(f"{args.id}: agora usando {instalador.reverter(ws.root, args.id)}")
        except instalador.Recusado as exc:
            print(f"recusado: {exc}", file=sys.stderr)
            return 2
    elif args.cmd == "historico":
        for e in instalador.historico(ws.root):
            print(e)
    elif args.cmd == "caminhos":
        print(":".join(instalador.caminhos(ws.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
