"""Host, Origin (mesma origem exata) e Fetch Metadata. Navegação direta (sem Origin) continua permitida."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_BODY = 1_000_000  # bytes; só vale com Content-Length (uvicorn não limita corpo chunked)
HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                                "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def add_security(app: FastAPI, settings) -> None:
    allowed = set(settings.allowed_hosts)

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":  # origem idêntica: esquema+host+porta
            return PlainTextResponse("origin não permitido", status_code=403)
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            return PlainTextResponse("corpo grande demais", status_code=413)
        if request.method not in SAFE_METHODS:
            if site and site not in ("same-origin", "none"):
                return PlainTextResponse("requisição cross-site recusada", status_code=403)
        elif site == "cross-site" and request.url.path not in ("/", "/dashboard"):
            return PlainTextResponse("leitura cross-site recusada", status_code=403)
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    # adicionado por último = executa primeiro: Host inválido nunca chega ao guard
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed))
