"""Agente OCR: extrai texto de imagens (screenshots, documentos). Referência: PP-OCR (PaddleOCR)."""
from __future__ import annotations

from typing import Any

from app.agents.multimodal import MediaAgent


class OcrAgent(MediaAgent):
    name = "ocr"
    actions = ("ocr_extract",)
    description = "Extração de texto de imagens PNG/JPEG (OCR)."
    backend_attr = "ocr"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        path = payload.get("path")
        if not isinstance(path, str):
            raise ValueError("payload.path é obrigatório")
        return await self.service.read_text(path)
