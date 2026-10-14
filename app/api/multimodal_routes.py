"""Rotas de status multimodal (a execução usa /run)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.multimodal.assets import LIMITS
from app.multimodal.service import MultimodalService


def build_multimodal_router(service: MultimodalService) -> APIRouter:
    api = APIRouter()

    @api.get("/multimodal/status")
    async def status():
        backends = {}
        for label in ("vision", "speech", "voice", "ocr", "clip"):
            be = getattr(service, label)
            ok, why = await asyncio.to_thread(be.probe) if be else (False, "não configurado")
            backends[label] = {"available": ok, "reason": why}
        return {"backends": backends, "limits_bytes": LIMITS, "index": service.index.stats()}

    return api
