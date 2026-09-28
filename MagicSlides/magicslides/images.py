"""Busca e download de imagens da internet.

Fontes gratuitas sem chave: Openverse (imagens Creative Commons) e
Wikimedia Commons. Com chave gratuita: Pexels, Unsplash e Pixabay.
As imagens baixadas são redimensionadas e embutidas no projeto como
data URL, para funcionarem offline e na exportação PPTX.
"""
from __future__ import annotations

import base64
import html
import io
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import __version__

USER_AGENT = f"MagicSlides/{__version__} (desktop presentation app; https://github.com/aldeirdemouracosta-maker/aldeir)"
MAX_DOWNLOAD = 15 * 1024 * 1024
TIMEOUT = 12


class ImageError(RuntimeError):
    pass


# ------------------------------------------------------------------ HTTP ---

def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read(5 * 1024 * 1024).decode("utf-8"))


def _check_public_url(url: str) -> None:
    """Evita que o backend seja usado para acessar a rede local (SSRF)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImageError("URL de imagem inválida.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ImageError(f"Não foi possível resolver {parsed.hostname}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ImageError("Endereço de imagem não permitido.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Revalida cada redirecionamento para não cair na rede local."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_image_opener = urllib.request.build_opener(_SafeRedirect)


def _strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


# ---------------------------------------------------------------- fontes ---

def _result(source: str, rid: str, title: str, thumb: str, url: str, width: Any, height: Any,
            author: str, license_: str, page: str) -> dict[str, Any]:
    return {
        "id": f"{source}:{rid}", "source": source, "title": (title or "").strip()[:200],
        "thumb": thumb or url, "url": url, "width": int(width or 0), "height": int(height or 0),
        "author": (author or "").strip()[:120], "license": (license_ or "").strip()[:60], "page": page or "",
    }


def search_openverse(query: str, per_page: int, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "page_size": per_page, "mature": "false"})
    data = _get_json(f"https://api.openverse.org/v1/images/?{params}")
    out = []
    for r in data.get("results", []):
        lic = f"CC {str(r.get('license', '')).upper()} {r.get('license_version') or ''}".strip()
        if str(r.get("license", "")).lower() in ("cc0", "pdm"):
            lic = str(r.get("license", "")).upper()
        out.append(_result("openverse", r.get("id", ""), r.get("title", ""), r.get("thumbnail", ""), r.get("url", ""),
                           r.get("width"), r.get("height"), r.get("creator", ""), lic, r.get("foreign_landing_url", "")))
    return out


def search_wikimedia(query: str, per_page: int, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": per_page,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600,
    })
    data = _get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        url = info.get("thumburl") or info.get("url")
        if not url or not re.search(r"\.(jpe?g|png|webp)$", url.split("?")[0], re.I):
            continue
        out.append(_result("wikimedia", str(p.get("pageid", "")), str(p.get("title", "")).removeprefix("File:"),
                           url, url, info.get("thumbwidth") or info.get("width"), info.get("thumbheight") or info.get("height"),
                           _strip_html((meta.get("Artist") or {}).get("value", "")),
                           (meta.get("LicenseShortName") or {}).get("value", ""), info.get("descriptionurl", "")))
    return out


def search_pexels(query: str, per_page: int, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    key = cfg.get("pexels_api_key")
    if not key:
        raise ImageError("Pexels precisa de chave (gratuita) em Configurações.")
    params = urllib.parse.urlencode({"query": query, "per_page": per_page, "orientation": "landscape"})
    data = _get_json(f"https://api.pexels.com/v1/search?{params}", {"Authorization": key})
    return [_result("pexels", str(p.get("id")), p.get("alt", ""), (p.get("src") or {}).get("medium", ""),
                    (p.get("src") or {}).get("large2x", ""), p.get("width"), p.get("height"),
                    p.get("photographer", ""), "Licença Pexels", p.get("url", "")) for p in data.get("photos", [])]


def search_unsplash(query: str, per_page: int, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    key = cfg.get("unsplash_access_key")
    if not key:
        raise ImageError("Unsplash precisa de chave (gratuita) em Configurações.")
    params = urllib.parse.urlencode({"query": query, "per_page": per_page, "orientation": "landscape"})
    data = _get_json(f"https://api.unsplash.com/search/photos?{params}", {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"})
    out = []
    for p in data.get("results", []):
        r = _result("unsplash", p.get("id", ""), p.get("alt_description") or p.get("description") or "",
                    (p.get("urls") or {}).get("small", ""), (p.get("urls") or {}).get("regular", ""),
                    p.get("width"), p.get("height"), (p.get("user") or {}).get("name", ""), "Licença Unsplash",
                    (p.get("links") or {}).get("html", ""))
        r["download_location"] = (p.get("links") or {}).get("download_location", "")
        out.append(r)
    return out


def search_pixabay(query: str, per_page: int, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    key = cfg.get("pixabay_api_key")
    if not key:
        raise ImageError("Pixabay precisa de chave (gratuita) em Configurações.")
    params = urllib.parse.urlencode({"key": key, "q": query[:100], "image_type": "photo", "orientation": "horizontal",
                                     "per_page": max(3, per_page), "safesearch": "true"})
    data = _get_json(f"https://pixabay.com/api/?{params}")
    return [_result("pixabay", str(h.get("id")), h.get("tags", ""), h.get("webformatURL", ""), h.get("largeImageURL", ""),
                    h.get("imageWidth"), h.get("imageHeight"), h.get("user", ""), "Licença Pixabay", h.get("pageURL", ""))
            for h in data.get("hits", [])]


SOURCES: dict[str, Callable[[str, int, dict[str, Any]], list[dict[str, Any]]]] = {
    "openverse": search_openverse,
    "wikimedia": search_wikimedia,
    "pexels": search_pexels,
    "unsplash": search_unsplash,
    "pixabay": search_pixabay,
}
SOURCE_LABELS = {"openverse": "Openverse (CC)", "wikimedia": "Wikimedia Commons", "pexels": "Pexels",
                 "unsplash": "Unsplash", "pixabay": "Pixabay"}


def configured_sources(cfg: dict[str, Any]) -> list[str]:
    """Fontes na ordem preferida. As que exigem chave entram na frente
    quando a chave existe (fotos de banco de imagens costumam ficar melhores)."""
    order = list(cfg.get("image_sources") or [])
    keyed = [("pexels", "pexels_api_key"), ("unsplash", "unsplash_access_key"), ("pixabay", "pixabay_api_key")]
    for name, key in reversed(keyed):
        if cfg.get(key) and name not in order:
            order.insert(0, name)
    return [s for s in order if s in SOURCES and (s not in dict(keyed) or cfg.get(dict(keyed)[s]))]


def search(query: str, cfg: dict[str, Any], source: str = "auto", per_page: int = 12) -> tuple[list[dict[str, Any]], list[str]]:
    """Devolve (resultados, avisos). Em "auto", junta as fontes configuradas."""
    query = " ".join((query or "").split())[:120]
    if not query:
        return [], ["Digite o que procurar."]
    names = configured_sources(cfg) if source == "auto" else [source]
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name in names:
        fn = SOURCES.get(name)
        if not fn:
            continue
        try:
            results.extend(fn(query, per_page, cfg))
        except ImageError as exc:
            warnings.append(str(exc))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            warnings.append(f"{SOURCE_LABELS.get(name, name)} indisponível ({getattr(exc, 'reason', exc)}).")
    return results, warnings


def candidates(query: str, cfg: dict[str, Any], landscape: bool = True, limit: int = 4) -> tuple[list[dict[str, Any]], list[str]]:
    """Melhores resultados da primeira fonte configurada que responder."""
    warnings: list[str] = []
    for name in configured_sources(cfg):
        try:
            items = SOURCES[name](query, 10, cfg)
        except ImageError as exc:
            warnings.append(str(exc))
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            warnings.append(f"{SOURCE_LABELS.get(name, name)} indisponível ({getattr(exc, 'reason', exc)}).")
            continue
        items = [i for i in items if i["url"]]
        if landscape:
            wide = [i for i in items if i["width"] >= i["height"] > 0]
            items = wide + [i for i in items if i not in wide]
        if items:
            return items[:limit], warnings
    return [], warnings


# -------------------------------------------------------------- download ---

def download_data_url(url: str, max_side: int = 1600) -> tuple[str, int, int]:
    """Baixa a imagem, reduz para no máximo `max_side` px e devolve
    (data URL PNG/JPEG, largura, altura)."""
    _check_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with _image_opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_DOWNLOAD + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ImageError(f"Falha ao baixar a imagem ({getattr(exc, 'reason', exc)}).") from exc
    if len(raw) > MAX_DOWNLOAD:
        raise ImageError("Imagem grande demais (limite 15 MB).")
    return encode_image(raw, max_side)


def encode_image(raw: bytes, max_side: int = 1600) -> tuple[str, int, int]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ImageError("Pillow não está instalado (pip install pillow).") from exc
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.load()
    except Exception as exc:
        raise ImageError("Arquivo de imagem inválido ou não suportado.") from exc
    img.thumbnail((max_side, max_side))
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    out = io.BytesIO()
    if has_alpha:
        img = img.convert("RGBA")
        img.save(out, "PNG", optimize=True)
        mime = "image/png"
    else:
        img = img.convert("RGB")
        img.save(out, "JPEG", quality=85, optimize=True, progressive=True)
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(out.getvalue()).decode('ascii')}", img.width, img.height


def credit_line(item: dict[str, Any]) -> str:
    parts = [item.get("title") or "Imagem"]
    if item.get("author"):
        parts.append(f"por {item['author']}")
    if item.get("license"):
        parts.append(f"({item['license']})")
    label = SOURCE_LABELS.get(item.get("source", ""), item.get("source", ""))
    line = " ".join(parts) + f" — {label}"
    if item.get("page"):
        line += f": {item['page']}"
    return line


def ping_unsplash_download(item: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Exigência das diretrizes da API Unsplash ao usar uma foto."""
    loc = item.get("download_location")
    key = cfg.get("unsplash_access_key")
    if not loc or not key:
        return
    try:
        _get_json(loc, {"Authorization": f"Client-ID {key}"})
    except Exception:
        pass


# ------------------------------------------------------- preencher slides ---

def fill_presentation_images(presentation: dict[str, Any], cfg: dict[str, Any],
                             progress: Callable[[str], None] | None = None) -> tuple[list[str], list[str]]:
    """Busca e baixa, em paralelo, uma imagem para cada elemento de imagem
    vazio. Elementos sem imagem viram um bloco de cor do tema.
    Devolve (créditos, avisos)."""
    todo = [(slide, el) for slide in presentation.get("slides", []) for el in slide.get("elements", [])
            if el.get("type") == "image" and not el.get("src") and el.get("query")]
    if not todo:
        return [], []
    used: set[str] = set()
    warnings: list[str] = []

    def work(pair):
        _, el = pair
        found, warns = candidates(el["query"], cfg, landscape=el["w"] >= el["h"])
        if not found:
            return el, found, None, warns
        try:
            return el, found, download_data_url(found[0]["url"])[0], warns
        except ImageError as exc:
            return el, found, None, warns + [str(exc)]

    credits: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(work, todo))
    for el, found, data_url, warns in results:
        for w in warns:
            if w not in warnings:
                warnings.append(w)
        chosen = found[0] if (found and data_url and found[0]["url"] not in used) else None
        if not chosen:
            # Mesma foto já usada em outro slide (ou falhou): tenta a próxima.
            data_url = None
            for item in found[1:] if found else []:
                if item["url"] in used:
                    continue
                try:
                    data_url = download_data_url(item["url"])[0]
                    chosen = item
                    break
                except ImageError:
                    continue
        if not chosen or not data_url:
            continue
        used.add(chosen["url"])
        el["src"] = data_url
        el["credit"] = credit_line(chosen)
        el["source"] = chosen["source"]
        el["page"] = chosen.get("page", "")
        credits.append(el["credit"])
        if chosen["source"] == "unsplash":
            ping_unsplash_download(chosen, cfg)
        if progress:
            progress(f"Imagem: {el['query']}")
    theme = presentation.get("theme", {})
    for slide in presentation.get("slides", []):
        for i, el in enumerate(slide.get("elements", [])):
            if el.get("type") == "image" and not el.get("src"):
                slide["elements"][i] = {
                    "id": el["id"].replace("image", "shape"), "type": "shape", "role": "surface-fill", "shape": "rect",
                    "x": el["x"], "y": el["y"], "w": el["w"], "h": el["h"],
                    "fill": theme.get("surface", "#DDDDDD"), "stroke": None, "opacity": 1, "radius": 0,
                    "placeholderQuery": el.get("query", ""),
                }
    return credits, warnings
