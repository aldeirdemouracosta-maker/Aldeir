"""Montagem da aplicação FastAPI."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.agents.chat import ChatAgent
from app.agents.coder import CoderAgent
from app.api.routes import build_router
from app.config import Settings, load_agent_config
from app.core.registry import AgentRegistry
from app.core.router import ActionRouter
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider


def build_provider(settings: Settings):
    cls = LocalCompatibleProvider if settings.provider == "local_compatible" else OllamaProvider
    return cls(settings.provider_url, settings.request_timeout)


def build_registry(settings: Settings, provider) -> AgentRegistry:
    cfg = load_agent_config(settings.agents_file)
    registry = AgentRegistry()
    for cls in (ChatAgent, CoderAgent):
        entry = cfg.get(cls.name, {})
        if entry.get("enabled", True):
            registry.register(cls(provider, entry.get("model", "")))
    return registry


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or Settings.from_env()
    provider = provider or build_provider(settings)
    registry = build_registry(settings, provider)
    app = FastAPI(title="SWARM LITE AI", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.include_router(build_router(registry, ActionRouter(registry), provider))
    return app


app = None  # uvicorn: use `uvicorn app.main:create_app --factory`
