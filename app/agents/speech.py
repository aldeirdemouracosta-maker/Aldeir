"""Agente SPEECH: transcrição local (referência: Whisper Tiny) com idioma detectado."""
from __future__ import annotations

from typing import Any

from app.agents.multimodal import MediaAgent


class SpeechAgent(MediaAgent):
    name = "speech"
    actions = ("speech_transcribe",)
    description = "Transcrição de áudio local, com idioma detectado."
    backend_attr = "speech"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        path = payload.get("path")
        if not isinstance(path, str):
            raise ValueError("payload.path é obrigatório")
        return await self.service.transcribe(path)
