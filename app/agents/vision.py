"""Agente VISION: descreve imagens locais PNG/JPEG (referência: SmolVLM 256M)."""
from __future__ import annotations

from typing import Any

from app.agents.multimodal import MediaAgent


class VisionAgent(MediaAgent):
    name = "vision"
    actions = ("image_describe",)
    description = "Descrição de imagens locais (PNG/JPEG)."
    backend_attr = "vision"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        path = payload.get("path")
        if not isinstance(path, str):
            raise ValueError("payload.path é obrigatório")
        return await self.service.describe_image(path, str(payload.get("prompt", "")))
