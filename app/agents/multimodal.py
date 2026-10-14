"""Base dos agentes de mídia: disponibilidade vem do backend opcional, nunca presumida."""
from __future__ import annotations

import asyncio

from app.agents.base import Agent
from app.multimodal.service import MultimodalService


class MediaAgent(Agent):
    backend_attr = ""

    def __init__(self, service: MultimodalService) -> None:
        self.service = service

    async def available(self) -> tuple[bool, str]:
        backend = getattr(self.service, self.backend_attr, None)
        if backend is None:
            return False, "backend não configurado"
        return await asyncio.to_thread(backend.probe)
