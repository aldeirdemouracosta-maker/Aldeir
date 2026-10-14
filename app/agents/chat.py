"""Agente CHAT: conversação, resumo e tradução."""
from __future__ import annotations

from typing import Any

from app.agents.base import TextAgent
from app.core.conversations import ConversationStore, check_session


class ChatAgent(TextAgent):
    name = "chat"
    actions = ("chat", "summarize", "translate")
    description = "Conversação (com memória por sessão), resumo e tradução."

    def __init__(self, provider, model: str, conversations: ConversationStore | None = None) -> None:
        super().__init__(provider, model)
        self.conversations = conversations

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
        session = payload.get("session")
        if session is None or self.conversations is None:
            return await self.provider.generate(self.model, text)
        check_session(session)
        history = self.conversations.history(session)
        reply = await self.provider.generate(self.model, text, history=history or None)
        if reply:  # só grava depois do sucesso: falha do modelo não deixa meia conversa na memória
            self.conversations.add(session, "user", text)
            self.conversations.add(session, "assistant", reply)
        return reply
