"""Consulta de lançamentos nas plataformas de código (somente leitura).

Cada plataforma tem uma API HTTP diferente para "qual é a última versão":
- GitHub:            GET /repos/{dono}/{repo}/releases/latest
                     (os arquivos trazem "digest": "sha256:..." desde 2025)
- GitLab:            GET /api/v4/projects/{dono%2Frepo}/releases
- Gitea/Forgejo/Codeberg: GET /api/v1/repos/{dono}/{repo}/releases/latest
- Hugging Face:      GET /api/models/{dono}/{repo}  (a "versão" é o commit)
                     e /api/models/{dono}/{repo}/tree/main (sha256 dos arquivos LFS)
Quando a plataforma não publica o sha256 de cada arquivo, procura-se no
lançamento um arquivo de somas (SHA256SUMS, checksums.txt...).
Mesma ideia do nvchecker (Arch Linux, MIT), em versão mínima com a
biblioteca padrão do Python.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

HOSTS_PADRAO = {"github": "https://api.github.com", "gitlab": "https://gitlab.com",
                "gitea": "https://codeberg.org", "huggingface": "https://huggingface.co"}
USER_AGENT = "minivideo-atualizar/1"
_SOMAS = re.compile(r"(sha256sums|checksums?)(\.txt)?$|\.sha256$", re.I)


@dataclass
class Arquivo:
    nome: str
    url: str
    tamanho: Optional[int] = None
    sha256: Optional[str] = None


@dataclass
class Lancamento:
    versao: str
    data: str = ""
    pagina: str = ""
    notas: str = ""
    arquivos: List[Arquivo] = field(default_factory=list)


class ErroFonte(RuntimeError):
    pass


class Cliente:
    """HTTP só leitura. ``permitir_http_local`` existe para os testes (servidor em 127.0.0.1)."""

    def __init__(self, timeout: float = 10, permitir_http_local: bool = False):
        self.timeout = timeout
        self.permitir_http_local = permitir_http_local

    def conferir_url(self, url: str) -> None:
        u = urllib.parse.urlparse(url)
        if u.scheme == "https":
            return
        if self.permitir_http_local and u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"):
            return
        raise ErroFonte(f"só HTTPS é aceito: {url}")

    def abrir(self, url: str):
        self.conferir_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=self.timeout)
        self.conferir_url(resp.geturl())  # redirecionamento também precisa ser HTTPS
        return resp

    def json(self, url: str):
        try:
            with self.abrir(url) as r:
                return json.loads(r.read(4 * 1024 * 1024).decode("utf-8"))
        except ErroFonte:
            raise
        except Exception as exc:  # rede, HTTP 4xx/5xx, JSON inválido
            raise ErroFonte(f"{type(exc).__name__}: {exc}") from exc

    def texto(self, url: str, limite: int = 256 * 1024) -> str:
        try:
            with self.abrir(url) as r:
                return r.read(limite).decode("utf-8", "replace")
        except Exception as exc:
            raise ErroFonte(f"{type(exc).__name__}: {exc}") from exc


def _sha(digest: Optional[str]) -> Optional[str]:
    if digest and digest.lower().startswith("sha256:"):
        h = digest.split(":", 1)[1].lower()
        return h if re.fullmatch(r"[0-9a-f]{64}", h) else None
    return None


def _completar_somas(cli: Cliente, lanc: Lancamento) -> None:
    """Preenche sha256 a partir de um arquivo de somas publicado no próprio lançamento."""
    if all(a.sha256 for a in lanc.arquivos):
        return
    for a in lanc.arquivos:
        if _SOMAS.search(a.nome):
            try:
                txt = cli.texto(a.url)
            except ErroFonte:
                return
            for linha in txt.splitlines():
                m = re.match(r"([0-9a-fA-F]{64})\s+\*?(\S+)", linha.strip())
                if m:
                    for b in lanc.arquivos:
                        if b.nome == m.group(2).split("/")[-1] and not b.sha256:
                            b.sha256 = m.group(1).lower()
            return


def github(cli: Cliente, repo: str, host: str) -> Lancamento:
    d = cli.json(f"{host}/repos/{repo}/releases/latest")
    return Lancamento(d["tag_name"], d.get("published_at") or "", d.get("html_url", ""), d.get("body") or "",
                      [Arquivo(a["name"], a["browser_download_url"], a.get("size"), _sha(a.get("digest")))
                       for a in d.get("assets", [])])


def gitlab(cli: Cliente, repo: str, host: str) -> Lancamento:
    lista = cli.json(f"{host}/api/v4/projects/{urllib.parse.quote(repo, safe='')}/releases?per_page=1")
    if not lista:
        raise ErroFonte("nenhum lançamento publicado")
    d = lista[0]
    links = (d.get("assets") or {}).get("links") or []
    return Lancamento(d["tag_name"], d.get("released_at") or "", (d.get("_links") or {}).get("self", ""),
                      d.get("description") or "",
                      [Arquivo(l["name"], l.get("direct_asset_url") or l["url"]) for l in links])


def gitea(cli: Cliente, repo: str, host: str) -> Lancamento:
    d = cli.json(f"{host}/api/v1/repos/{repo}/releases/latest")
    return Lancamento(d["tag_name"], d.get("published_at") or "", d.get("html_url", ""), d.get("body") or "",
                      [Arquivo(a["name"], a["browser_download_url"], a.get("size")) for a in d.get("assets", [])])


def huggingface(cli: Cliente, repo: str, host: str) -> Lancamento:
    d = cli.json(f"{host}/api/models/{repo}")
    arquivos = []
    try:
        for e in cli.json(f"{host}/api/models/{repo}/tree/main"):
            if e.get("type") == "file":
                lfs = e.get("lfs") or {}
                arquivos.append(Arquivo(e["path"], f"{host}/{repo}/resolve/main/{e['path']}",
                                        lfs.get("size") or e.get("size"), lfs.get("oid")))
    except ErroFonte:
        pass
    return Lancamento(d["sha"][:12], d.get("lastModified") or "", f"{host}/{repo}", "", arquivos)


FORJAS = {"github": github, "gitlab": gitlab, "gitea": gitea, "forgejo": gitea, "codeberg": gitea,
          "huggingface": huggingface}


def consultar(cli: Cliente, fonte: Dict) -> Lancamento:
    tipo = fonte["forja"]
    if tipo not in FORJAS:
        raise ErroFonte(f"plataforma desconhecida: {tipo}")
    padrao = HOSTS_PADRAO["gitea" if tipo in ("forgejo", "codeberg") else tipo]
    host = fonte.get("host", padrao).rstrip("/")
    lanc = FORJAS[tipo](cli, fonte["repo"], host)
    _completar_somas(cli, lanc)
    return lanc


def _tokens(v: str):
    v = re.sub(r"^(v|b|release-|version-)", "", v.strip().lower())
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.findall(r"\d+|[a-z]+", v)]


def mais_nova(disponivel: str, instalada: str) -> bool:
    """Comparação natural: 1.10 > 1.9; b8200 > b8117; v0.2.6.0 > v0.2.5.0; 20240101 > 20221029."""
    a, b = _tokens(disponivel), _tokens(instalada)
    if not a or not b:
        return disponivel != instalada
    return a > b
