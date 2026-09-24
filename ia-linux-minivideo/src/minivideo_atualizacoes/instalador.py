"""Instalação de ferramentas na partição de dados, atômica e reversível.

Passos (cada um pode recusar):
1. dependências: glibc mínima, Vulkan (como o "Depends:" de um pacote);
2. download HTTPS com limite de tamanho, para a pasta cache;
3. sha256 conferido com o publicado pela plataforma (sem hash publicado:
   só com confirmação explícita, registrada no histórico);
4. extração segura (zip sem caminhos absolutos, "..", nem links) numa pasta
   nova Ferramentas/<id>/<versão>, nunca por cima da versão em uso;
5. teste: o binário novo precisa executar (SIGILL = instrução que a CPU não
   tem, ex.: AVX2 no Xeon X79);
6. troca atômica do link Ferramentas/<id>/atual (rename(2)): ou vale a
   versão antiga ou a nova, nunca um meio-termo. É a ideia do OSTree, em
   pequena escala. "reverter" aponta o link de volta.
O sistema do ISO (em RAM) não é alterado; as ferramentas novas entram no
PATH antes das do ISO (ver caminhos()).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import time
import zipfile
from typing import Dict, List, Optional

from . import forjas, indice

LIMITE_MIB = 1024
MANTER_VERSOES = 2


class Recusado(RuntimeError):
    pass


def _raiz(ws_root: str, item_id: str) -> str:
    return os.path.join(ws_root, "Ferramentas", item_id)


def _glibc() -> Optional[tuple]:
    try:
        v = os.confstr("CS_GNU_LIBC_VERSION")  # "glibc 2.44"
        return tuple(int(x) for x in v.split()[1].split(".")[:2])
    except (ValueError, OSError, AttributeError, IndexError):
        return None


def conferir_requisitos(item: Dict) -> List[str]:
    problemas = []
    req = item.get("requer") or {}
    if "glibc" in req:
        tem, precisa = _glibc(), tuple(int(x) for x in str(req["glibc"]).split("."))
        if tem is None or tem < precisa:
            problemas.append(f"precisa de glibc >= {req['glibc']} (tem {'.'.join(map(str, tem)) if tem else '?'})")
    if req.get("vulkan") and not any(os.path.exists(p) for p in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d")):
        problemas.append("precisa de Vulkan (nenhum driver ICD instalado)")
    return problemas


def historico(ws_root: str) -> List[Dict]:
    caminho = os.path.join(indice.pasta(ws_root), "historico.jsonl")
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _registrar(ws_root: str, evento: Dict) -> None:
    evento = {"em": time.strftime("%Y-%m-%dT%H:%M:%S"), **evento}
    with open(os.path.join(indice.pasta(ws_root), "historico.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(evento, ensure_ascii=False) + "\n")


def baixar(cli: forjas.Cliente, arq: Dict, destino: str, limite_mib: int = LIMITE_MIB) -> str:
    """Baixa para ``destino`` e devolve o sha256 calculado."""
    if arq.get("tamanho") and arq["tamanho"] > limite_mib * 1024 * 1024:
        raise Recusado(f"arquivo maior que o limite de {limite_mib} MiB")
    h = hashlib.sha256()
    total = 0
    parcial = destino + ".part"
    try:
        with cli.abrir(arq["url"]) as r, open(parcial, "wb") as out:
            while True:
                bloco = r.read(1024 * 1024)
                if not bloco:
                    break
                total += len(bloco)
                if total > limite_mib * 1024 * 1024:
                    raise Recusado(f"download passou do limite de {limite_mib} MiB")
                h.update(bloco)
                out.write(bloco)
    except Recusado:
        os.unlink(parcial)
        raise
    except Exception as exc:
        if os.path.exists(parcial):
            os.unlink(parcial)
        raise Recusado(f"falha no download: {exc}") from exc
    os.replace(parcial, destino)
    return h.hexdigest()


def _extrair_zip(zpath: str, destino: str) -> None:
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            nome = info.filename
            if nome.startswith("/") or ".." in nome.split("/"):
                raise Recusado(f"zip com caminho inseguro: {nome}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise Recusado(f"zip com link simbólico: {nome}")
        z.extractall(destino)


def _achar_binario(pasta: str, nome: str) -> Optional[str]:
    for raiz, _, arquivos in os.walk(pasta):
        if nome in arquivos:
            return os.path.join(raiz, nome)
    return None


def testar(binario: str, argumentos: List[str]) -> None:
    try:
        r = subprocess.run([binario, *argumentos], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)
    except subprocess.TimeoutExpired:
        return  # executou (só demorou): não é incompatibilidade de CPU
    except OSError as exc:
        raise Recusado(f"o binário novo não executa: {exc}") from exc
    if r.returncode < 0:
        sig = signal.Signals(-r.returncode).name
        dica = " (instrução que esta CPU não tem, ex.: AVX2)" if sig == "SIGILL" else ""
        raise Recusado(f"o binário novo morreu com {sig}{dica}")


def _trocar_link(raiz: str, versao: str) -> None:
    tmp = os.path.join(raiz, ".atual.novo")
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(versao, tmp)
    os.replace(tmp, os.path.join(raiz, "atual"))


def _limpar(raiz: str, manter: List[str]) -> None:
    versoes = sorted((d for d in os.listdir(raiz) if not d.startswith(".") and d != "atual"
                      and os.path.isdir(os.path.join(raiz, d))),
                     key=lambda d: os.path.getmtime(os.path.join(raiz, d)), reverse=True)
    for d in versoes[MANTER_VERSOES:]:
        if d not in manter:
            shutil.rmtree(os.path.join(raiz, d), ignore_errors=True)


def aplicar(ws_root: str, item: Dict, linha: Dict, cli: Optional[forjas.Cliente] = None,
            aceitar_sem_hash: bool = False) -> str:
    """Instala a versão do índice (``linha``) do ``item``. Devolve a versão ativada."""
    cli = cli or forjas.Cliente(timeout=60)
    if item["tipo"] != "ferramenta":
        raise Recusado({"compilado": "compilado dentro do ISO: chega com a próxima versão do ISO",
                        "modelo": "modelos não são baixados aqui: use minivideo-modelos instrucoes <id>",
                        "sistema": "o sistema roda da RAM: grave o ISO novo no pendrive"}.get(
                            item["tipo"], f"tipo {item['tipo']} não é instalável"))
    arq, versao = linha.get("arquivo"), linha.get("disponivel")
    if not arq or not versao:
        raise Recusado(linha.get("erro") or "índice sem arquivo para instalar; rode 'verificar' antes")
    if not all(c.isalnum() or c in "._-+" for c in versao):
        raise Recusado(f"versão com caracteres inválidos: {versao!r}")
    problemas = conferir_requisitos(item)
    if problemas:
        raise Recusado("; ".join(problemas))
    if not arq.get("sha256") and not aceitar_sem_hash:
        raise Recusado("a plataforma não publicou sha256 deste arquivo; confirme para instalar mesmo assim")

    raiz = _raiz(ws_root, item["id"])
    final = os.path.join(raiz, versao)
    if os.path.exists(final):
        _trocar_link(raiz, versao)
        _registrar(ws_root, {"acao": "ativar", "id": item["id"], "versao": versao})
        return versao
    cache = os.path.join(indice.pasta(ws_root), "cache")
    os.makedirs(cache, exist_ok=True)
    baixado = os.path.join(cache, os.path.basename(arq["nome"]))
    sha = baixar(cli, arq, baixado)
    if arq.get("sha256") and sha != arq["sha256"]:
        os.unlink(baixado)
        raise Recusado(f"sha256 não confere (esperado {arq['sha256'][:16]}…, obtido {sha[:16]}…)")

    staging = os.path.join(raiz, f".staging-{versao}")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(os.path.join(staging, "bin"))
    try:
        if item["formato"] == "zip":
            _extrair_zip(baixado, os.path.join(staging, "pacote"))
            alvo = _achar_binario(os.path.join(staging, "pacote"), item["binario"])
            if not alvo:
                raise Recusado(f"{item['binario']} não está no zip")
            os.chmod(alvo, 0o755)
            os.symlink(os.path.relpath(alvo, os.path.join(staging, "bin")), os.path.join(staging, "bin", item["binario"]))
        else:
            alvo = os.path.join(staging, "bin", item["binario"])
            shutil.copyfile(baixado, alvo)
            os.chmod(alvo, 0o755)
        testar(os.path.join(staging, "bin", item["binario"]), item.get("teste", ["--version"]))
        with open(os.path.join(staging, "origem.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": item["id"], "versao": versao, "url": arq["url"], "sha256": sha,
                       "sha256_publicado": arq.get("sha256"), "fonte": item["fonte"]}, fh, indent=2)
        os.replace(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if os.path.exists(baixado):
            os.unlink(baixado)
    anterior = versao_ativa(ws_root, item["id"])
    _trocar_link(raiz, versao)
    _registrar(ws_root, {"acao": "instalar", "id": item["id"], "versao": versao, "anterior": anterior,
                         "sha256": sha, "sha256_publicado": bool(arq.get("sha256"))})
    _limpar(raiz, [versao, anterior or ""])
    return versao


def versao_ativa(ws_root: str, item_id: str) -> Optional[str]:
    link = os.path.join(_raiz(ws_root, item_id), "atual")
    return os.path.basename(os.readlink(link)) if os.path.islink(link) else None


def reverter(ws_root: str, item_id: str) -> str:
    """Volta para a versão anterior. Sem anterior na partição: volta para a do ISO."""
    raiz = _raiz(ws_root, item_id)
    atual = versao_ativa(ws_root, item_id)
    if not atual:
        raise Recusado("nenhuma versão instalada na partição: já está usando a do ISO")
    anteriores = [e.get("anterior") for e in reversed(historico(ws_root))
                  if e.get("id") == item_id and e.get("acao") == "instalar" and e.get("versao") == atual]
    alvo = next((a for a in anteriores if a and os.path.isdir(os.path.join(raiz, a))), None)
    if alvo:
        _trocar_link(raiz, alvo)
    else:
        os.unlink(os.path.join(raiz, "atual"))  # sem link: vale o binário do ISO
    _registrar(ws_root, {"acao": "reverter", "id": item_id, "de": atual, "para": alvo or "ISO"})
    return alvo or "ISO"


def caminhos(ws_root: str) -> List[str]:
    """Pastas bin/ das versões ativas, para ir na frente do PATH."""
    base = os.path.join(ws_root, "Ferramentas")
    if not os.path.isdir(base):
        return []
    return sorted(os.path.join(base, d, "atual", "bin") for d in os.listdir(base)
                  if os.path.isdir(os.path.join(base, d, "atual", "bin")))


def ativar_path(ws_root: str) -> None:
    extras = [p for p in caminhos(ws_root) if p not in os.environ.get("PATH", "").split(":")]
    if extras:
        os.environ["PATH"] = ":".join(extras + [os.environ.get("PATH", "")])
