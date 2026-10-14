"""Dashboard local: arquivos estáticos nativos (HTML/CSS/JS), somente leitura."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_dashboard_router() -> APIRouter:
    api = APIRouter()

    @api.get("/", include_in_schema=False)
    @api.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")

    return api
