"""Host, Origin e Fetch Metadata. Navegação direta (sem Origin) continua permitida."""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def add_security(app: FastAPI, settings) -> None:
    allowed = set(settings.allowed_hosts)

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        if origin and urlparse(origin).hostname not in allowed:
            return PlainTextResponse("origin não permitido", status_code=403)
        if request.method not in SAFE_METHODS:
            if site and site not in ("same-origin", "none"):
                return PlainTextResponse("requisição cross-site recusada", status_code=403)
        elif site == "cross-site" and request.url.path not in ("/", "/dashboard"):
            return PlainTextResponse("leitura cross-site recusada", status_code=403)
        return await call_next(request)

    # adicionado por último = executa primeiro: Host inválido nunca chega ao guard
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed))
