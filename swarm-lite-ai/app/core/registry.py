"""AgentRegistry: registro dinâmico com validação de nomes e ações."""
from __future__ import annotations

import re

from app.agents.base import Agent
from app.core.models import RegistryError

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._actions: dict[str, str] = {}  # ação -> nome do agente

    def register(self, agent: Agent) -> None:
        if not NAME_RE.match(agent.name):
            raise RegistryError(f"nome de agente inválido: {agent.name!r}")
        if agent.name in self._agents:
            raise RegistryError(f"agente já registrado: {agent.name}")
        if not agent.actions:
            raise RegistryError(f"agente sem ações: {agent.name}")
        for action in agent.actions:
            if not NAME_RE.match(action):
                raise RegistryError(f"ação inválida: {action!r}")
            owner = self._actions.get(action)
            if owner:
                raise RegistryError(f"ação duplicada {action!r} (já pertence a {owner})")
        self._agents[agent.name] = agent
        for action in agent.actions:
            self._actions[action] = agent.name

    def unregister(self, name: str) -> None:
        agent = self._agents.pop(name, None)
        if agent is None:
            raise RegistryError(f"agente não registrado: {name}")
        for action in agent.actions:
            self._actions.pop(action, None)

    def get(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError:
            raise RegistryError(f"agente não registrado: {name}") from None

    def owner_of(self, action: str) -> str | None:
        return self._actions.get(action)

    def names(self) -> list[str]:
        return sorted(self._agents)

    def actions(self) -> dict[str, str]:
        return dict(self._actions)
