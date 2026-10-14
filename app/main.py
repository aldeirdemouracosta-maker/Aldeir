"""Montagem da aplicação FastAPI."""
from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agents.chat import ChatAgent
from app.agents.langid import LangIdAgent
from app.agents.ocr import OcrAgent
from app.agents.planner import PlannerAgent, RunContext
from app.agents.retrieval import RetrievalAgent
from app.agents.coder import CoderAgent
from app.agents.rag import RagAgent
from app.agents.speech import SpeechAgent
from app.agents.vision import VisionAgent
from app.agents.voice import VoiceAgent
from app.api.multimodal_routes import build_multimodal_router
from app.api.routes import build_router
from app.api.security import add_security
from app.config import Settings, load_agent_config
from app.dashboard import STATIC_DIR, build_dashboard_router
from app.core.coordination import ResourceCoordinator
from app.core.manager import AgentManager, AgentSpec, ModelManager
from app.core.memory import MemoryManager
from app.core.orchestrator import Orchestrator
from app.core.scheduler import ResourceScheduler
from app.core.registry import AgentRegistry
from app.core.resources import ResourceMonitor
from app.core.router import ActionRouter
from app.core.state import StateStore
from app.multimodal.assets import AssetStore
from app.multimodal.documents import DocumentIndex
from app.multimodal.executors import (ChineseClipBackend, KokoroBackend, PaddleOcrBackend, SmolVLMBackend,
                                      WhisperBackend)
from app.multimodal.service import MultimodalService
from app.providers.local_compatible import LocalCompatibleProvider
from app.providers.ollama import OllamaProvider


def build_provider(settings: Settings):
    cls = LocalCompatibleProvider if settings.provider == "local_compatible" else OllamaProvider
    return cls(settings.provider_url, settings.request_timeout)


def build_service(settings: Settings, provider, vision=None, speech=None, voice=None,
                  index: DocumentIndex | None = None, ocr=None, clip=None) -> MultimodalService:
    media = settings.media_dir or Path(tempfile.mkdtemp(prefix="swarm-media-"))
    if index is None:
        index = DocumentIndex(media.parent / "index.db" if settings.media_dir else ":memory:")
    return MultimodalService(AssetStore(media), index, provider, settings.embed_model,
                             vision or SmolVLMBackend(), speech or WhisperBackend(), voice or KokoroBackend(),
                             ocr or PaddleOcrBackend(), clip or ChineseClipBackend())


def build_specs(service: MultimodalService, registry: AgentRegistry, ctx: RunContext) -> dict[str, AgentSpec]:
    text = lambda cls: AgentSpec(cls.name, cls.actions, cls)
    media = lambda cls: AgentSpec(cls.name, cls.actions, lambda _p, _m: cls(service), text_model=False)
    planner = AgentSpec(PlannerAgent.name, PlannerAgent.actions,
                        lambda p, m: PlannerAgent(p, m, registry, ctx))
    plain = AgentSpec(LangIdAgent.name, LangIdAgent.actions, lambda _p, _m: LangIdAgent(), text_model=False)
    return {s.name: s for s in (text(ChatAgent), text(CoderAgent), media(VisionAgent), media(SpeechAgent),
                                media(VoiceAgent), media(RagAgent), media(OcrAgent), plain, planner,
                                media(RetrievalAgent))}


def build_manager(settings: Settings, provider, store: StateStore | None = None,
                  service: MultimodalService | None = None, ctx: RunContext | None = None) -> AgentManager:
    store = store or StateStore(settings.state_path or ":memory:")
    service = service or build_service(settings, provider)
    registry = AgentRegistry()
    return AgentManager(registry, build_specs(service, registry, ctx or RunContext()), provider, store,
                        load_agent_config(settings.agents_file))


def build_registry(settings: Settings, provider) -> AgentRegistry:
    """Registro somente-leitura para a CLI (sem persistir alterações)."""
    return build_manager(settings, provider, StateStore(":memory:")).registry


def build_orchestrator(settings: Settings, router: ActionRouter,
                       memory: MemoryManager | None = None) -> Orchestrator:
    memory = memory or MemoryManager(settings.headroom_mb)
    coord = ResourceCoordinator(settings.coord_dir, settings.coord_capacity,
                               ttl=settings.job_timeout * 2 + 60) if settings.coord_dir else None
    sched = ResourceScheduler(memory, settings.max_concurrent, settings.max_queue)
    return Orchestrator(router, sched, settings.job_timeout, coord, queue_timeout=settings.queue_timeout)


def create_app(settings: Settings | None = None, provider=None,
               monitor: ResourceMonitor | None = None,
               service: MultimodalService | None = None,
               memory: MemoryManager | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    provider = provider or build_provider(settings)
    service = service or build_service(settings, provider)
    ctx = RunContext()
    manager = build_manager(settings, provider, service=service, ctx=ctx)
    @asynccontextmanager
    async def lifespan(_app):
        yield
        close = getattr(provider, "aclose", None)
        if close:
            await close()

    app = FastAPI(title="SWARM LITE AI", docs_url=None, redoc_url=None, lifespan=lifespan)
    add_security(app, settings)
    router = ActionRouter(manager.registry)
    orchestrator = build_orchestrator(settings, router, memory)
    ctx.run_step = orchestrator.run_nested
    app.include_router(build_router(manager, orchestrator, ModelManager(provider),
                                    monitor or ResourceMonitor()))
    app.include_router(build_multimodal_router(service))
    app.include_router(build_dashboard_router())
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
