"""Agente CHAT: conversação, resumo e tradução."""
from __future__ import annotations

from typing import Any

from app.agents.base import TextAgent


class ChatAgent(TextAgent):
    name = "chat"
    actions = ("chat", "summarize", "translate")
    description = "Conversação, resumo e tradução."

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        text = self.text_of(payload)
        if action == "summarize":
            return await self.provider.generate(
                self.model, text, system="Resuma o texto de forma curta e fiel.")
        if action == "translate":
            target = payload.get("target", "português")
            return await self.provider.generate(
                self.model, text,
                system=f"Traduza para {target}. Responda somente com a tradução.")
        return await self.provider.generate(self.model, text)
