"""Servidor HTTP local do MagicSlides (só escuta em 127.0.0.1).

Toda rota /api exige o cabeçalho X-MagicSlides-Token, gerado a cada
execução e injetado na página. Isso impede que outros sites abertos no
navegador usem o servidor local (CSRF / DNS rebinding).
"""
from __future__ import annotations

import json
import secrets
import sys
import threading
import time
import traceback
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import APP_NAME, __version__, ai, config, images
from .core import default_presentation, normalize_presentation, validate_presentation
from .html_export import build_html
from .layouts import build_credits_slide, build_presentation
from .pptx_export import build_pptx
from .themes import list_themes


def resource_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # executável PyInstaller
    return Path(base) / "magicslides" if base else Path(__file__).resolve().parent


STATIC = resource_dir() / "static"
MAX_BODY = 120 * 1024 * 1024
TOKEN = secrets.token_urlsafe(24)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _safe_filename(title: str, ext: str) -> str:
    title = str(title or APP_NAME).strip() or APP_NAME
    safe = "".join(c if c.isalnum() or c in "-_ " else "-" for c in title).strip().replace(" ", "-")[:80]
    return f"{safe or APP_NAME}.{ext}"


# ------------------------------------------------------------------ jobs ---

def _update_job(job_id: str, **fields: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def run_generation(job_id: str, req: dict[str, Any]) -> None:
    try:
        cfg = config.effective()
        provider_label = {"anthropic": "Claude", "openai": "o modelo de IA", "offline": "o modo offline"}.get(cfg["provider"], "IA")
        _update_job(job_id, message=f"Escrevendo o roteiro com {provider_label}…", progress=0.1)
        outline, used = ai.generate_outline(
            req.get("prompt", ""), int(req.get("slides") or 8),
            req.get("language") or cfg.get("language") or "Português do Brasil",
            req.get("tone") or "", cfg,
        )
        _update_job(job_id, message="Montando os layouts…", progress=0.45)
        if not req.get("images", True):
            for spec in outline["slides"]:
                spec["image_query"] = ""
                if spec["layout"] in ("image-right", "image-left"):
                    spec["layout"] = "bullets"
                elif spec["layout"] == "image-full":
                    spec["layout"] = "section"
        pres = build_presentation(outline, req.get("theme"), author=cfg.get("author", ""))
        warnings: list[str] = []
        if req.get("images", True):
            total = sum(1 for s in pres["slides"] for e in s["elements"] if e.get("type") == "image")
            done = {"n": 0}

            def progress(msg: str) -> None:
                done["n"] += 1
                _update_job(job_id, message=f"Buscando imagens na internet ({done['n']}/{total})…",
                            progress=0.5 + 0.45 * done["n"] / max(1, total))

            _update_job(job_id, message=f"Buscando imagens na internet (0/{total})…", progress=0.5)
            credits, warnings = images.fill_presentation_images(pres, cfg, progress)
            if credits and req.get("credits", True):
                pres["slides"].append(build_credits_slide(credits, pres["theme"]))
        errors = validate_presentation(pres)
        if errors:
            raise RuntimeError("Apresentação gerada inválida: " + "; ".join(errors[:3]))
        _update_job(job_id, state="done", message="Pronto!", progress=1.0, result=pres, warnings=warnings, provider=used)
    except (ai.AIError, images.ImageError) as exc:
        _update_job(job_id, state="error", message=str(exc))
    except Exception as exc:  # erro inesperado: mostra algo útil em vez de travar
        traceback.print_exc()
        _update_job(job_id, state="error", message=f"Erro inesperado: {exc}")


def start_job(req: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        for old in [k for k, v in JOBS.items() if time.time() - v["created"] > 3600]:
            JOBS.pop(old, None)
        JOBS[job_id] = {"state": "running", "message": "Iniciando…", "progress": 0.0, "created": time.time()}
    threading.Thread(target=run_generation, args=(job_id, req), daemon=True).start()
    return job_id


# --------------------------------------------------------------- handler ---

class Handler(SimpleHTTPRequestHandler):
    server_version = f"{APP_NAME}/{__version__}"
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    # ---- segurança
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def _token_ok(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-MagicSlides-Token", ""), TOKEN)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path).path
        if parsed == "/":
            parsed = "/index.html"
        resolved = (STATIC / Path(parsed.lstrip("/")).as_posix()).resolve()
        try:
            resolved.relative_to(STATIC.resolve())
        except ValueError:
            return str(STATIC.resolve() / "__blocked__")
        return str(resolved)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    # ---- respostas
    def _json(self, status: int, obj: Any) -> None:
        blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _file(self, blob: bytes, ctype: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _error(self, status: int, msg: str) -> None:
        self._json(status, {"ok": False, "errors": [msg]})

    # ---- GET
    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "Host não permitido")
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__MS_TOKEN__", TOKEN)
            blob = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
            return
        if path == "/api/health":
            return self._json(200, {"ok": True, "app": APP_NAME, "version": __version__})
        if path.startswith("/api/"):
            if not self._token_ok():
                return self._error(403, "Token inválido")
            if path == "/api/default":
                return self._json(200, default_presentation())
            if path == "/api/themes":
                return self._json(200, {"themes": list_themes()})
            if path == "/api/settings":
                return self._json(200, self._settings_view())
            if path.startswith("/api/jobs/"):
                with JOBS_LOCK:
                    job = dict(JOBS.get(path.rsplit("/", 1)[-1]) or {})
                if not job:
                    return self._error(404, "Tarefa não encontrada")
                job.pop("created", None)
                return self._json(200, job)
            return self._error(404, "Endpoint não encontrado")
        return super().do_GET()

    def _settings_view(self) -> dict[str, Any]:
        view = config.public_view()
        view["image_source_labels"] = images.SOURCE_LABELS
        return view

    # ---- POST
    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "Host não permitido")
        if not self._token_ok():
            return self._error(403, "Token inválido")
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return self._error(400, "Content-Length inválido")
        if length < 0:
            return self._error(400, "Content-Length inválido")
        if length > MAX_BODY:
            return self._error(413, "Arquivo grande demais (limite 120 MB).")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return self._error(400, "JSON inválido")
        path = urlparse(self.path).path
        try:
            return self._route_post(path, payload)
        except (ai.AIError, images.ImageError) as exc:
            return self._error(422, str(exc))
        except Exception as exc:
            traceback.print_exc()
            return self._error(500, f"Erro interno: {exc}")

    def _route_post(self, path: str, payload: Any):
        if path == "/api/settings":
            if not isinstance(payload, dict):
                return self._error(400, "Configuração inválida")
            config.save(payload)
            return self._json(200, self._settings_view())
        if path == "/api/generate":
            if not isinstance(payload, dict) or not str(payload.get("prompt", "")).strip():
                return self._error(400, "Descreva o tema ou cole um texto.")
            return self._json(200, {"ok": True, "job": start_job(payload)})
        if path == "/api/images/search":
            results, warnings = images.search(str(payload.get("query", "")), config.effective(),
                                              str(payload.get("source") or "auto"))
            return self._json(200, {"ok": True, "results": results, "warnings": warnings})
        if path == "/api/images/fetch":
            item = payload.get("item") or {}
            src, w, h = images.download_data_url(str(item.get("url", "")))
            if item.get("source") == "unsplash":
                images.ping_unsplash_download(item, config.effective())
            return self._json(200, {"ok": True, "src": src, "width": w, "height": h,
                                    "credit": images.credit_line(item)})
        if path == "/api/images/encode":
            data_url = str(payload.get("dataUrl", ""))
            if "," not in data_url:
                return self._error(400, "Imagem inválida")
            import base64
            raw = base64.b64decode(data_url.split(",", 1)[1])
            src, w, h = images.encode_image(raw, 2000)
            return self._json(200, {"ok": True, "src": src, "width": w, "height": h})

        data = normalize_presentation(payload)
        errors = validate_presentation(data)
        if errors:
            return self._json(422, {"ok": False, "errors": errors})
        title = data.get("meta", {}).get("title")
        if path == "/api/validate":
            return self._json(200, {"ok": True, "slides": len(data["slides"]), "presentation": data})
        if path == "/api/export/html":
            return self._file(build_html(data), "text/html; charset=utf-8", _safe_filename(title, "html"))
        if path == "/api/export/pptx":
            return self._file(build_pptx(data),
                              "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                              _safe_filename(title, "pptx"))
        return self._error(404, "Endpoint não encontrado")

    def log_message(self, fmt, *args):
        if "/api/jobs/" in (self.path or ""):
            return
        sys.stderr.write(f"[{APP_NAME}] {fmt % args}\n")


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Por segurança, o MagicSlides só escuta em 127.0.0.1.")
    try:
        return ThreadingHTTPServer((host, port), Handler)
    except OSError:
        return ThreadingHTTPServer((host, 0), Handler)  # porta ocupada: usa uma livre
