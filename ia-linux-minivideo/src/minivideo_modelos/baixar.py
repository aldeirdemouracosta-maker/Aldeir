"""Download de modelos pedido pelo usuário (tecla M ou minivideo-modelos baixar).

Só modelos de arquivo único com repositório no Hugging Face (Whisper, Qwen
GGUF). O arquivo é escolhido pela lista do repositório (API /tree), que
também traz o sha256 (objeto LFS) e o tamanho: o download é conferido e só
então renomeado para o nome final. Modelos generativos (vários arquivos,
CUDA) continuam com instruções manuais.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from typing import Dict, List, Optional

from minivideo_atualizacoes import forjas, instalador

from . import gerenciador as g

HF = "https://huggingface.co"
RESERVA_MIB = 2048


class Recusado(RuntimeError):
    pass


def _entrada(modelo_id: str) -> Dict:
    m = {x["id"]: x for x in g.catalogo()}.get(modelo_id)
    if m is None:
        raise Recusado(f"modelo desconhecido: {modelo_id}")
    if m.get("embutido"):
        raise Recusado("já vem no ISO: nada a baixar")
    if not m.get("repo_hf"):
        raise Recusado("modelo com vários arquivos ou só para CUDA: use 'minivideo-modelos instrucoes " + modelo_id + "'")
    return m


def escolher(m: Dict, cli: forjas.Cliente, host: str = HF) -> Dict:
    """Arquivo do repositório que casa com ``arquivo`` do catálogo (preferências na ordem)."""
    lista = cli.json(f"{host}/api/models/{m['repo_hf']}/tree/main")
    candidatos: List[Dict] = [e for e in lista if e.get("type") == "file"
                              and fnmatch.fnmatch(e["path"].split("/")[-1], m["arquivo"])]
    if not candidatos:
        raise Recusado(f"nenhum arquivo {m['arquivo']} em {m['repo_hf']}")
    for pref in m.get("preferir", []):
        achados = [e for e in candidatos if pref.lower() in e["path"].lower()]
        if achados:
            candidatos = achados
            break
    e = sorted(candidatos, key=lambda x: (x.get("lfs") or {}).get("size") or x.get("size") or 0)[0]
    lfs = e.get("lfs") or {}
    return {"nome": e["path"].split("/")[-1], "url": f"{host}/{m['repo_hf']}/resolve/main/{e['path']}",
            "tamanho": lfs.get("size") or e.get("size"), "sha256": lfs.get("oid")}


def baixar(modelos_dir: str, modelo_id: str, cli: Optional[forjas.Cliente] = None, host: str = HF,
           aceitar_sem_hash: bool = False, arquivo: Optional[Dict] = None) -> str:
    """Baixa, confere e instala em Modelos/<destino>/. Devolve o caminho final."""
    m = _entrada(modelo_id)
    cli = cli or forjas.Cliente(timeout=60)
    arq = arquivo or escolher(m, cli, host)
    destino_dir = os.path.join(modelos_dir, m["destino"])
    final = os.path.join(destino_dir, os.path.basename(arq["nome"]))
    if os.path.exists(final):
        raise Recusado(f"já existe: {final}")
    if not arq.get("sha256") and not aceitar_sem_hash:
        raise Recusado("o Hugging Face não informou sha256 deste arquivo; confirme para baixar mesmo assim")
    os.makedirs(destino_dir, exist_ok=True)
    tamanho_mib = (arq.get("tamanho") or 0) / 1048576
    livre = shutil.disk_usage(destino_dir).free / 1048576
    if tamanho_mib and livre - tamanho_mib < RESERVA_MIB:
        raise Recusado(f"espaço insuficiente: {livre:.0f} MiB livres, o arquivo tem {tamanho_mib:.0f} MiB "
                       f"(reserva de {RESERVA_MIB} MiB)")
    limite = int(tamanho_mib * 1.05) + 16 if tamanho_mib else 8192
    temp = final + ".baixando"
    try:
        sha = instalador.baixar(cli, arq, temp, limite_mib=limite)
    except instalador.Recusado as exc:
        raise Recusado(str(exc)) from exc
    if arq.get("sha256") and sha != arq["sha256"]:
        os.unlink(temp)
        raise Recusado(f"sha256 não confere (esperado {arq['sha256'][:16]}…, obtido {sha[:16]}…)")
    os.replace(temp, final)
    return final
