"""Agente VOICE: síntese local (referência: Kokoro ONNX) com saída WAV."""
from __future__ import annotations

from typing import Any

from app.agents.multimodal import MediaAgent


class VoiceAgent(MediaAgent):
    name = "voice"
    actions = ("voice_speak", "voice_list")
    description = "Síntese de voz local em WAV e listagem de vozes."
    backend_attr = "voice"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        if action == "voice_list":
            return "\n".join(await self.service.list_voices())
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("payload.text é obrigatório")
        return await self.service.speak(text, str(payload.get("voice", "default")))
