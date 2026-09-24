"""minivideo-preparar-disco: cria a partição de dados MV_DADOS.

APAGA o disco escolhido. Proteções:
- só discos inteiros, graváveis e com pelo menos 8 GiB;
- recusa o disco de onde o sistema deu boot (ISO/pendrive MINIVIDEO) e
  qualquer disco com partição montada;
- mostra modelo, tamanho e partições atuais, e exige digitar
  "APAGAR <nome>" (ex.: APAGAR sdb);
- exige root (no ISO: sair da interface com Q e escolher [p]).
Depois: GPT com uma partição ext4 rotulada MV_DADOS, montada em /data.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional

ROTULO = "MV_DADOS"
MINIMO_GIB = 8
Runner = Callable[..., subprocess.CompletedProcess]


class Recusado(RuntimeError):
    pass


def ler_lsblk(runner: Runner = subprocess.run) -> Dict:
    r = runner(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,TYPE,RM,RO,MODEL,TRAN,MOUNTPOINTS,LABEL,FSTYPE"],
               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return json.loads(r.stdout)


def _montagens(no: Dict) -> List[str]:
    m = [x for x in (no.get("mountpoints") or []) if x]
    for filho in no.get("children") or []:
        m += _montagens(filho)
    return m


def _rotulos(no: Dict) -> List[str]:
    r = [x for x in (no.get("label"), no.get("fstype")) if x]
    for filho in no.get("children") or []:
        r += _rotulos(filho)
    return r


def discos(lsblk: Dict) -> List[Dict]:
    out = []
    for d in lsblk.get("blockdevices", []):
        if d.get("type") != "disk" or d["name"].startswith(("zram", "loop", "ram", "sr")):
            continue
        montado = _montagens(d)
        rot = _rotulos(d)
        motivos = []
        if d.get("ro"):
            motivos.append("somente leitura")
        if int(d.get("size") or 0) < MINIMO_GIB * 1024 ** 3:
            motivos.append(f"menor que {MINIMO_GIB} GiB")
        if "MINIVIDEO" in rot or "iso9660" in rot or "/" in montado:
            motivos.append("é o disco de onde o sistema deu boot")
        elif montado:
            motivos.append("tem partição montada: " + ", ".join(montado))
        out.append({"nome": d["name"], "caminho": d.get("path") or f"/dev/{d['name']}",
                    "gib": round(int(d.get("size") or 0) / 1024 ** 3, 1), "modelo": (d.get("model") or "").strip(),
                    "conexao": d.get("tran") or "", "removivel": bool(d.get("rm")),
                    "ja_mv_dados": ROTULO in rot, "particoes": [
                        f"{c['name']} {round(int(c.get('size') or 0) / 1024 ** 3, 1)} GiB {c.get('fstype') or ''} "
                        f"{c.get('label') or ''}".strip() for c in d.get("children") or []],
                    "recusa": motivos})
    return out


def particao(disco: str) -> str:
    return disco + ("p1" if disco[-1].isdigit() else "1")  # nvme0n1 → nvme0n1p1; sdb → sdb1


def comandos(disco: str) -> List[Dict]:
    part = particao(disco)
    return [{"cmd": ["wipefs", "-a", disco]},
            {"cmd": ["sfdisk", "--wipe", "always", disco], "entrada": "label: gpt\n,,L\n"},
            {"cmd": ["mkfs.ext4", "-F", "-L", ROTULO, part]}]


def preparar(nome: str, confirmacao: str, runner: Runner = subprocess.run, lsblk: Optional[Dict] = None,
             exigir_root: bool = True, esperar=time.sleep, achar: Callable = shutil.which) -> str:
    if exigir_root and os.geteuid() != 0:
        raise Recusado("precisa de root: saia da interface (Q) e escolha [p]")
    lista = discos(lsblk if lsblk is not None else ler_lsblk(runner))
    alvo = next((d for d in lista if d["nome"] == nome or d["caminho"] == nome), None)
    if not alvo:
        raise Recusado(f"{nome} não é um disco inteiro listado (use o nome, ex.: sdb)")
    if alvo["recusa"]:
        raise Recusado(f"{alvo['nome']}: " + "; ".join(alvo["recusa"]))
    if confirmacao.strip() != f"APAGAR {alvo['nome']}":
        raise Recusado(f"confirmação errada: digite exatamente APAGAR {alvo['nome']}")
    cmds = comandos(alvo["caminho"])
    faltam = [c["cmd"][0] for c in cmds if not achar(c["cmd"][0])]
    if faltam:  # confere antes de começar: nunca deixa o disco apagado pela metade
        raise Recusado("ferramentas ausentes: " + ", ".join(faltam))
    for c in cmds:
        r = runner(c["cmd"], input=(c.get("entrada") or "").encode(), stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT)
        if r.returncode != 0:
            raise Recusado(f"{' '.join(c['cmd'])} falhou: {r.stdout.decode(errors='replace')[-400:]}")
        if c["cmd"][0] == "sfdisk":
            esperar(2)  # o kernel relê a tabela; devtmpfs cria o nó da partição
    return particao(alvo["caminho"])


def _mostrar(lista: List[Dict]) -> None:
    for d in lista:
        estado = "PODE PREPARAR" if not d["recusa"] else "recusado: " + "; ".join(d["recusa"])
        extra = " · já tem MV_DADOS" if d["ja_mv_dados"] else ""
        print(f"{d['nome']:<10} {d['gib']:>8} GiB  {d['conexao']:<6} {d['modelo'] or '(sem modelo)'}"
              f"{' · removível' if d['removivel'] else ''}{extra}\n           {estado}")
        for p in d["particoes"]:
            print(f"           - {p}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="minivideo-preparar-disco", description="Cria a partição MV_DADOS (APAGA o disco).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar", help="discos e se podem ser preparados (não altera nada)")
    s = sub.add_parser("preparar", help="apaga o disco e cria a partição MV_DADOS")
    s.add_argument("disco", help="nome do disco, ex.: sdb ou nvme0n1")
    s.add_argument("--confirmar", metavar='"APAGAR <nome>"', help="sem isso, a confirmação é pedida no terminal")
    a = p.parse_args(argv)
    try:
        lista = discos(ler_lsblk())
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"lsblk falhou: {exc}", file=sys.stderr)
        return 1
    if a.cmd == "listar":
        _mostrar(lista)
        return 0
    alvo = next((d for d in lista if d["nome"] == a.disco), None)
    if alvo:
        _mostrar([alvo])
    conf = a.confirmar
    if conf is None:
        print(f"\nTUDO em {a.disco} será APAGADO. Para continuar digite: APAGAR {a.disco}")
        conf = input("> ")
    try:
        part = preparar(a.disco, conf)
    except Recusado as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    print(f"Pronto: {part} (ext4, rótulo {ROTULO}).")
    if not os.path.ismount("/data"):
        os.makedirs("/data", exist_ok=True)
        if subprocess.run(["mount", "-o", "noatime", part, "/data"]).returncode == 0:
            ativar_dados("/data/minivideo")
            print("Montada em /data. A interface usa /data/minivideo a partir da próxima abertura "
                  "(arquivos que estavam na RAM não são movidos).")
    return 0


def ativar_dados(raiz: str, env: str = "/run/minivideo.env") -> None:
    """Mesmo que o S30minivideo faz no boot: pastas, dono e MINIVIDEO_HOME para a sessão."""
    import pwd
    from minivideo_agents.workspace import FOLDERS
    for f in FOLDERS:
        os.makedirs(os.path.join(raiz, f), exist_ok=True)
    try:
        u = pwd.getpwnam("minivideo")
        for base, dirs, _ in os.walk(raiz):
            os.chown(base, u.pw_uid, u.pw_gid)
    except (KeyError, PermissionError):
        pass
    with open(env, "w") as fh:
        fh.write(f"MINIVIDEO_HOME={raiz}\n")


if __name__ == "__main__":
    sys.exit(main())
