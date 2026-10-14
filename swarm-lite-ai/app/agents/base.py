"""Contrato dos agentes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.providers.base import Provider


class Agent(ABC):
    name: str
    actions: tuple[str, ...]
    description: str = ""

    async def available(self) -> tuple[bool, str]:
        """(disponível, motivo). Agentes opcionais devem sobrescrever."""
        return True, "ok"

    @abstractmethod
    async def run(self, action: str, payload: dict[str, Any]) -> str: ...


class TextAgent(Agent):
    """Agente baseado em um modelo de texto de um provedor."""

    def __init__(self, provider: Provider, model: str) -> None:
        self.provider = provider
        self.model = model

    async def available(self) -> tuple[bool, str]:
        try:
            installed = await self.provider.list_models()
        except Exception as e:  # provedor fora do ar não derruba o runtime
            return False, str(e)
        if self.model not in installed:
            return False, f"modelo {self.model!r} não instalado"
        return True, "ok"

    @staticmethod
    def text_of(payload: dict[str, Any]) -> str:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("payload.text é obrigatório")
        return text
