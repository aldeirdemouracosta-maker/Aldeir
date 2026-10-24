"""Servidor HTTP local do LumePDF: recebe os arquivos, roda as ferramentas e devolve o resultado."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import core
from .core import PdfError

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 500 * 1024 * 1024

# nome da ferramenta -> (função(workdir, files, params) -> (Path, nome sugerido))
def _stem(files) -> str:
    return Path(files[0]["name"]).stem


def _one(files):
    if len(files) != 1:
        raise PdfError("Selecione exatamente 1 arquivo.")
    return files[0]


def _t_merge(wd, files, p):
    out = wd / "unido.pdf"
    core.merge([f["path"] for f in files], out)
    return out, "unido.pdf"


def _t_split(wd, files, p):
    f = _one(files)
    out = wd / "dividido.zip"
    core.split(f["path"], p.get("ranges", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_dividido.zip"


def _t_extract(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.extract_pages(f["path"], p.get("ranges", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_paginas.pdf"


def _t_delete(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.delete_pages(f["path"], p.get("ranges", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_editado.pdf"


def _t_reorder(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.reorder(f["path"], p.get("order", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_reordenado.pdf"


def _t_rotate(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.rotate(f["path"], int(p.get("angle", 90)), p.get("ranges", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_girado.pdf"


def _t_compress(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.compress(f["path"], p.get("level", "leve"), out, p.get("password", ""))
    return out, f"{_stem(files)}_comprimido.pdf"


def _t_img2pdf(wd, files, p):
    out = wd / "out.pdf"
    core.images_to_pdf([f["path"] for f in files], out)
    return out, "imagens.pdf"


def _t_pdf2img(wd, files, p):
    f = _one(files)
    out = wd / "imagens.zip"
    core.pdf_to_images(f["path"], p.get("format", "jpg"), int(p.get("dpi", 150)),
                       p.get("ranges", ""), out, p.get("password", ""))
    return out, f"{_stem(files)}_imagens.zip"


def _t_text(wd, files, p):
    f = _one(files)
    out = wd / "out.txt"
    core.extract_text(f["path"], out, p.get("password", ""))
    return out, f"{_stem(files)}.txt"


def _t_watermark(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.watermark(f["path"], p.get("text", ""), out, p.get("password", ""),
                   float(p.get("opacity", 0.2)), int(p.get("size", 60)))
    return out, f"{_stem(files)}_marca.pdf"


def _t_numbers(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.page_numbers(f["path"], out, p.get("password", ""))
    return out, f"{_stem(files)}_numerado.pdf"


def _t_protect(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.protect(f["path"], p.get("new_password", ""), out)
    return out, f"{_stem(files)}_protegido.pdf"


def _t_unlock(wd, files, p):
    f = _one(files)
    out = wd / "out.pdf"
    core.unlock(f["path"], p.get("password", ""), out)
    return out, f"{_stem(files)}_desbloqueado.pdf"


TOOLS = {
    "merge": _t_merge, "split": _t_split, "extract": _t_extract, "delete": _t_delete,
    "reorder": _t_reorder, "rotate": _t_rotate, "compress": _t_compress,
    "img2pdf": _t_img2pdf, "pdf2img": _t_pdf2img, "text": _t_text,
    "watermark": _t_watermark, "numbers": _t_numbers, "protect": _t_protect, "unlock": _t_unlock,
}

_CONTENT_TYPES = {".pdf": "application/pdf", ".zip": "application/zip", ".txt": "text/plain; charset=utf-8",
                  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                  ".jpg": "image/jpeg", ".png": "image/png"}
_ID = re.compile(r"^[0-9a-f]{32}$")


class Workspace:
    """Pasta temporária com os uploads e resultados da sessão."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="lumepdf_"))
        self.files: dict[str, dict] = {}
        self.results: dict[str, tuple[Path, str]] = {}

    def add_upload(self, name: str, data: bytes) -> dict:
        fid = uuid.uuid4().hex
        safe = re.sub(r'[\\/:*?"<>|]', "_", Path(name).name) or "arquivo"
        path = self.root / f"{fid}_{safe}"
        path.write_bytes(data)
        entry = {"id": fid, "name": safe, "path": path}
        self.files[fid] = entry
        return entry

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "LumePDF"
    ws: Workspace

    def log_message(self, *a):  # silencioso
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            m = re.fullmatch(r"/api/thumb/([0-9a-f]{32})/(\d+)", path)
            if m:
                f = self.ws.files.get(m.group(1))
                if not f:
                    return self._json(404, {"error": "Arquivo não encontrado."})
                q = parse_qs(url.query)
                data = core.render_thumbnail(f["path"], int(m.group(2)), int(q.get("w", ["180"])[0]),
                                             q.get("pw", [""])[0])
                return self._send(200, data, "image/jpeg")
            m = re.fullmatch(r"/download/([0-9a-f]{32})", path)
            if m and m.group(1) in self.ws.results:
                p, name = self.ws.results[m.group(1)]
                return self._send(200, p.read_bytes(), _CONTENT_TYPES.get(p.suffix, "application/octet-stream"),
                                  {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
            self._json(404, {"error": "Não encontrado."})
        except PdfError as exc:
            self._json(400, {"error": str(exc)})

    def _static(self, rel: str):
        target = (STATIC / rel).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            return self._json(404, {"error": "Não encontrado."})
        self._send(200, target.read_bytes(), _CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

    def do_POST(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json(413, {"error": "Arquivo grande demais (máx. 500 MB)."})
        body = self.rfile.read(length)
        try:
            if url.path == "/api/upload":
                name = parse_qs(url.query).get("name", ["arquivo"])[0]
                entry = self.ws.add_upload(name, body)
                is_pdf = body[:5] == b"%PDF-"
                meta = core.info(entry["path"]) if is_pdf else {"pages": 0, "encrypted": False}
                return self._json(200, {"id": entry["id"], "name": entry["name"], "pdf": is_pdf, **meta})
            m = re.fullmatch(r"/api/tool/(\w+)", url.path)
            if m and m.group(1) in TOOLS:
                req = json.loads(body or b"{}")
                files = []
                for fid in req.get("files", []):
                    if not _ID.match(str(fid)) or fid not in self.ws.files:
                        raise PdfError("Arquivo não encontrado. Envie-o novamente.")
                    files.append(self.ws.files[fid])
                if not files:
                    raise PdfError("Selecione ao menos um arquivo.")
                rid = uuid.uuid4().hex
                wd = self.ws.root / rid
                wd.mkdir()
                out, name = TOOLS[m.group(1)](wd, files, req.get("params", {}))
                self.ws.results[rid] = (out, name)
                return self._json(200, {"download": f"/download/{rid}", "name": name,
                                        "size": out.stat().st_size})
            self._json(404, {"error": "Ferramenta desconhecida."})
        except PdfError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # arquivo corrompido etc.
            self._json(500, {"error": f"Falha ao processar o PDF: {exc}"})


def make_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    ws = Workspace()
    handler = type("BoundHandler", (Handler,), {"ws": ws})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.workspace = ws
    return srv
