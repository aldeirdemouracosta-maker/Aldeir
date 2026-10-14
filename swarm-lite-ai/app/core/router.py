"""ActionRouter: roteamento determinístico pela tabela de ações. Sem LLM."""
from __future__ import annotations

from app.agents.base import Agent
from app.core.models import RouteError
from app.core.registry import AgentRegistry


class ActionRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def route(self, action: str) -> Agent:
        owner = self._registry.owner_of(action)
        if owner is None:
            raise RouteError(f"ação desconhecida: {action!r}")
        return self._registry.get(owner)
