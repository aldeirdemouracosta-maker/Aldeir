"""Manifestos e instalação segura de arquivos de modelo.

Regras (do PDF de pesquisa): baixar UM arquivo, nunca `git clone`; exigir SHA-256; recusar > 1 GB sem
autorização explícita; só hosts oficiais; retomar download parcial; nunca guardar pesos no Git.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from app.core.models import SwarmError

MAX_AUTO_BYTES = 1024 * 2**20
ALLOWED_HOST = re.compile(r"(^|\.)(huggingface\.co|hf\.co)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ModelFileError(SwarmError):
    pass


@dataclass
class Manifest:
    id: str
    agents: list[str]
    size_mb: float
    license: str
    status: str
    url: str | None = None
    filename: str | None = None
    sha256: str | None = None
    languages: list[str] = field(default_factory=list)
    source: str | None = None
    backend: str = ""


def load_manifests(path: Path) -> dict[str, Manifest]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    known = Manifest.__dataclass_fields__
    out: dict[str, Manifest] = {}
    for m in raw.get("models", []):
        out[m["id"]] = Manifest(**{k: v for k, v in m.items() if k in known})
    return out


def installed_path(m: Manifest, models_dir: Path) -> Path | None:
    if not m.filename:
        return None
    p = models_dir / m.id / m.filename
    return p if p.is_file() else None


def _host_ok(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and bool(ALLOWED_HOST.search(u.hostname or ""))


async def install(m: Manifest, models_dir: Path, *, sha256: str | None = None, allow_large: bool = False,
                  client: httpx.AsyncClient | None = None) -> Path:
    """Baixa o arquivo do manifesto para models_dir/<id>/<filename>, verificando o SHA-256."""
    if not m.url or not m.filename:
        raise ModelFileError(f"{m.id}: sem URL de arquivo único; baixe manualmente de {m.source or 'a fonte oficial'}")
    if not FILENAME_RE.match(m.filename):
        raise ModelFileError(f"{m.id}: nome de arquivo inválido")
    expected = (sha256 or m.sha256 or "").lower()
    if not SHA_RE.match(expected):
        raise ModelFileError(f"{m.id}: informe o SHA-256 (64 hex) da página oficial com --sha256; nada foi baixado")
    if m.size_mb * 2**20 > MAX_AUTO_BYTES and not allow_large:
        raise ModelFileError(f"{m.id}: acima de 1 GB; use autorização explícita (--allow-large)")
    if not _host_ok(m.url):
        raise ModelFileError(f"{m.id}: host não permitido")
    dest = models_dir / m.id / m.filename
    if dest.is_file() and _sha256_file(dest) == expected:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(dest.parent).free < m.size_mb * 2**20 * 1.1:
        raise ModelFileError(f"{m.id}: espaço em disco insuficiente")
    part = dest.with_suffix(dest.suffix + ".part")
    own = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        await _download(client, m.url, part, allow_large)
    finally:
        if own:
            await client.aclose()
    if _sha256_file(part) != expected:
        part.unlink(missing_ok=True)
        raise ModelFileError(f"{m.id}: SHA-256 não confere; arquivo descartado")
    part.replace(dest)
    return dest


async def _download(client: httpx.AsyncClient, url: str, part: Path, allow_large: bool) -> None:
    have = part.stat().st_size if part.exists() else 0
    for _ in range(5):  # redirecionamentos manuais: cada salto precisa ser um host permitido
        headers = {"Range": f"bytes={have}-"} if have else {}
        async with client.stream("GET", url, headers=headers, follow_redirects=False) as r:
            if r.status_code in (301, 302, 303, 307, 308):
                url = str(r.url.join(r.headers["location"]))
                if not _host_ok(url):
                    raise ModelFileError("redirecionamento para host não permitido")
                continue
            if r.status_code == 416:  # já completo
                return
            if r.status_code not in (200, 206):
                raise ModelFileError(f"download falhou: HTTP {r.status_code}")
            if r.status_code == 200:  # servidor ignorou Range: recomeça
                have = 0
                part.unlink(missing_ok=True)
            total = have + int(r.headers.get("content-length", 0))
            if total > MAX_AUTO_BYTES and not allow_large:
                raise ModelFileError("arquivo acima de 1 GB; autorização explícita necessária")
            with part.open("ab") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
            return
    raise ModelFileError("redirecionamentos demais")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def remove(m: Manifest, models_dir: Path) -> bool:
    d = models_dir / m.id
    if not d.is_dir() or d.resolve().parent != models_dir.resolve():
        return False
    shutil.rmtree(d)
    return True
