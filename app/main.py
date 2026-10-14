"""Montagem da aplicação FastAPI."""
from __future__ import annotations

from fastapi import FastAPI

from app.agents.chat import ChatAgent
from app.agents.coder import CoderAgent
from app.api.routes import build_router
from app.api.security import add_security
from app.config import Settings, load_agent_config
from app.core.manager import AgentManager, ModelManager
from app.core.registry import AgentRegistry
from app.core.resources import ResourceMonitor
from app.core.router import ActionRouter
from app.core.state import StateStore
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider

AGENT_CLASSES = {c.name: c for c in (ChatAgent, CoderAgent)}


def build_provider(settings: Settings):
    cls = LocalCompatibleProvider if settings.provider == "local_compatible" else OllamaProvider
    return cls(settings.provider_url, settings.request_timeout)


def build_manager(settings: Settings, provider, store: StateStore | None = None) -> AgentManager:
    store = store or StateStore(settings.state_path or ":memory:")
    return AgentManager(AgentRegistry(), AGENT_CLASSES, provider, store,
                        load_agent_config(settings.agents_file))


def build_registry(settings: Settings, provider) -> AgentRegistry:
    """Registro somente-leitura para a CLI (sem persistir alterações)."""
    return build_manager(settings, provider, StateStore(":memory:")).registry


def create_app(settings: Settings | None = None, provider=None,
               monitor: ResourceMonitor | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    provider = provider or build_provider(settings)
    manager = build_manager(settings, provider)
    app = FastAPI(title="SWARM LITE AI", docs_url=None, redoc_url=None)
    add_security(app, settings)
    app.include_router(build_router(manager, ActionRouter(manager.registry),
                                    ModelManager(provider), monitor or ResourceMonitor()))
    return app
