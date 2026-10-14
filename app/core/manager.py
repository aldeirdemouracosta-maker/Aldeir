"""AgentManager (ativar/desativar, modelo por agente) e ModelManager (modelos do provedor)."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from app.agents.base import Agent
from app.core.models import ProviderError, SwarmError
from app.core.registry import AgentRegistry
from app.core.state import StateStore


class ManagerError(SwarmError):
    pass


class UnknownAgent(ManagerError):
    pass


class ModelManager:
    """Consulta o provedor. Nunca baixa, carrega nem descarrega modelos."""

    def __init__(self, provider) -> None:
        self.provider = provider

    async def installed(self) -> list[str]:
        return await self.provider.list_models()

    async def loaded(self) -> list[str]:
        fn = getattr(self.provider, "loaded_models", None)
        return await fn() if fn else []


@dataclass(frozen=True)
class AgentSpec:
    name: str
    actions: tuple[str, ...]
    build: Callable[[object, str], Agent]  # (provider, modelo) -> agente
    text_model: bool = True  # False: o modelo do agente não é um modelo de texto trocável


class AgentManager:
    def __init__(self, registry: AgentRegistry, factories: dict[str, AgentSpec], provider,
                 store: StateStore, defaults: dict[str, dict]) -> None:
        self.registry, self.factories, self.provider, self.store = registry, factories, provider, store
        saved = store.agent_states()
        self._state: dict[str, dict] = {}
        for name in factories:  # estado salvo prevalece sobre o YAML
            d = defaults.get(name, {})
            self._state[name] = {"enabled": d.get("enabled", True), "model": d.get("model", ""),
                                 **saved.get(name, {})}
            if self._state[name]["enabled"]:
                self._instantiate(name)

    def _instantiate(self, name: str) -> None:
        self.registry.register(self.factories[name].build(self.provider, self._state[name]["model"]))

    def _check(self, name: str) -> None:
        if name not in self.factories:
            raise UnknownAgent(f"agente desconhecido: {name}")

    def _persist(self, name: str, event: str) -> None:
        self.store.set_agent_state(name, self._state[name])
        self.store.log_event(event, {"agent": name, **self._state[name]})

    def status(self) -> list[dict]:
        return [{"name": n, **self._state[n], "actions": list(self.factories[n].actions)}
                for n in sorted(self.factories)]

    def enable(self, name: str) -> None:
        self._check(name)
        if not self._state[name]["enabled"]:
            self._instantiate(name)
            self._state[name]["enabled"] = True
            self._persist(name, "agent.enabled")

    def disable(self, name: str) -> None:
        self._check(name)
        if self._state[name]["enabled"]:
            self.registry.unregister(name)
            self._state[name]["enabled"] = False
            self._persist(name, "agent.disabled")

    async def set_model(self, name: str, model: str) -> None:
        self._check(name)
        if not self.factories[name].text_model:
            raise ManagerError(f"agente {name} não usa modelo de texto")
        if not isinstance(model, str) or not model.strip():
            raise ManagerError("modelo vazio")
        try:
            installed = await self.provider.list_models()
        except ProviderError as e:
            raise ManagerError(f"não foi possível verificar modelos: {e}") from e
        if model not in installed:
            raise ManagerError(f"modelo {model!r} não instalado (nada será baixado automaticamente)")
        self._state[name]["model"] = model
        if self._state[name]["enabled"]:
            self.registry.get(name).model = model
        self._persist(name, "agent.model_changed")
