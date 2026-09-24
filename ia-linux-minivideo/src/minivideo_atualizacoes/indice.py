"""Índice de atualizações: o equivalente ao "apt update".

Consulta cada fonte (em paralelo, só leitura), compara com a versão
instalada e grava ``Ferramentas/_atualizacoes/indice.json``. Nada é baixado
nem instalado aqui.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from . import forjas

PACOTE = os.path.dirname(__file__)


def pasta(ws_root: str) -> str:
    p = os.path.join(ws_root, "Ferramentas", "_atualizacoes")
    os.makedirs(p, exist_ok=True)
    return p


def carregar_fontes(ws_root: Optional[str] = None) -> List[Dict]:
    with open(os.path.join(PACOTE, "fontes.json"), encoding="utf-8") as fh:
        itens = json.load(fh)["itens"]
    if ws_root:
        extra = os.path.join(pasta(ws_root), "fontes.json")
        if os.path.exists(extra):
            with open(extra, encoding="utf-8") as fh:
                ids = {i["id"] for i in itens}
                itens += [i for i in json.load(fh).get("itens", []) if i["id"] not in ids]
    return itens


RELEASE = "/etc/minivideo-release"


def ler_release(caminho: str = RELEASE) -> Dict[str, str]:
    out = {}
    try:
        with open(caminho, encoding="utf-8") as fh:
            for linha in fh:
                k, _, v = linha.strip().partition("=")
                if k:
                    out[k] = v.strip().strip('"')
    except OSError:
        pass
    return out


def versao_atual(ws_root: str, item: Dict) -> Optional[str]:
    """Versão ativa na partição de dados (Ferramentas/<id>/atual) ou a do ISO."""
    if item["tipo"] == "sistema":
        return ler_release(os.environ.get("MINIVIDEO_RELEASE", RELEASE)).get("VERSION") or item.get("instalada")
    link = os.path.join(ws_root, "Ferramentas", item["id"], "atual")
    if os.path.islink(link):
        return os.path.basename(os.readlink(link))
    return item.get("instalada")


def _escolher_arquivo(item: Dict, lanc: forjas.Lancamento) -> Optional[forjas.Arquivo]:
    padrao = item.get("arquivo")
    cpu = ler_release(os.environ.get("MINIVIDEO_RELEASE", RELEASE)).get("CPU", "")
    if cpu and item.get(f"arquivo_{cpu}"):
        padrao = item[f"arquivo_{cpu}"]  # ISO da mesma variante de CPU que está rodando
    if not padrao:
        return None
    for a in lanc.arquivos:
        if re.search(padrao, a.nome):
            return a
    return None


def _uma(cli: forjas.Cliente, ws_root: str, item: Dict) -> Dict:
    atual = versao_atual(ws_root, item)
    linha = {"id": item["id"], "tipo": item["tipo"], "forja": item["fonte"]["forja"],
             "repo": item["fonte"]["repo"], "instalada": atual, "disponivel": None, "novo": False,
             "pagina": "", "data": "", "arquivo": None, "erro": None}
    try:
        lanc = forjas.consultar(cli, item["fonte"])
    except (forjas.ErroFonte, KeyError) as exc:
        linha["erro"] = str(exc)
        return linha
    linha.update(disponivel=lanc.versao, pagina=lanc.pagina, data=lanc.data, notas=lanc.notas[:2000])
    if item["fonte"]["forja"] == "huggingface":
        linha["novo"] = bool(atual) and atual != lanc.versao
    else:
        linha["novo"] = bool(atual) and forjas.mais_nova(lanc.versao, atual)
    arq = _escolher_arquivo(item, lanc)
    if arq:
        linha["arquivo"] = {"nome": arq.nome, "url": arq.url, "tamanho": arq.tamanho, "sha256": arq.sha256}
        extras = {"somas": item.get("somas"), "assinatura": item.get("assinatura")}
        for chave, nome in extras.items():
            achado = next((a for a in lanc.arquivos if nome and a.nome == nome), None)
            if achado:
                linha[chave] = {"nome": achado.nome, "url": achado.url, "tamanho": achado.tamanho}
    elif item["tipo"] in ("ferramenta", "sistema"):
        linha["erro"] = "lançamento sem arquivo para Linux x86_64 com o nome esperado"
    return linha


def atualizar_indice(ws_root: str, cli: Optional[forjas.Cliente] = None,
                     fontes: Optional[List[Dict]] = None) -> Dict:
    cli = cli or forjas.Cliente()
    fontes = fontes if fontes is not None else carregar_fontes(ws_root)
    etags = os.path.join(pasta(ws_root), "etags.json")
    cli.carregar_etags(etags)
    with ThreadPoolExecutor(max_workers=6) as ex:
        linhas = list(ex.map(lambda it: _uma(cli, ws_root, it), fontes))
    cli.salvar_etags(etags)
    doc = {"formato": "minivideo-indice/1", "consultado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "sem_mudanca_304": cli.respostas_304, "itens": linhas}
    caminho = os.path.join(pasta(ws_root), "indice.json")
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
    return doc


def ler_indice(ws_root: str) -> Optional[Dict]:
    try:
        with open(os.path.join(pasta(ws_root), "indice.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
