"""Rotas HTTP. A lógica fica em core/; aqui só tradução para HTTP."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.manager import AgentManager, ManagerError, ModelManager
from app.core.models import ProviderError, RouteError, TaskResult
from app.core.resources import ResourceMonitor
from app.core.router import ActionRouter


class RunBody(BaseModel):
    action: str
    payload: dict = Field(default_factory=dict)


class ModelBody(BaseModel):
    model: str


def build_router(manager: AgentManager, router: ActionRouter, models: ModelManager,
                 monitor: ResourceMonitor) -> APIRouter:
    api = APIRouter()
    registry = manager.registry

    @api.get("/health")
    async def health():
        return {"status": "ok", "agents": len(registry.names())}

    @api.get("/agents")
    async def agents():
        out = []
        for name in registry.names():
            agent = registry.get(name)
            ok, reason = await agent.available()
            out.append({"name": name, "actions": list(agent.actions),
                        "description": agent.description, "available": ok, "reason": reason})
        return out

    @api.get("/management/agents")
    async def management_agents():
        out = []
        for s in manager.status():
            ok, reason = (await registry.get(s["name"]).available()) if s["enabled"] else (False, "desativado")
            out.append({**s, "available": ok, "reason": reason})
        return out

    @api.post("/management/agents/{name}/enable")
    async def enable(name: str):
        return _managed(lambda: manager.enable(name), name)

    @api.post("/management/agents/{name}/disable")
    async def disable(name: str):
        return _managed(lambda: manager.disable(name), name)

    @api.put("/management/agents/{name}/model")
    async def set_model(name: str, body: ModelBody):
        try:
            await manager.set_model(name, body.model)
        except ManagerError as e:
            raise HTTPException(status_code=_code(e), detail=str(e)) from e
        return {"agent": name, "model": body.model}

    def _managed(fn, name):
        try:
            fn()
        except ManagerError as e:
            raise HTTPException(status_code=_code(e), detail=str(e)) from e
        return {"agent": name, "ok": True}

    def _code(e: ManagerError) -> int:
        return 404 if "desconhecido" in str(e) else 409

    @api.get("/management/models")
    async def management_models():
        try:
            return {"installed": await models.installed(), "loaded": await models.loaded()}
        except ProviderError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

    @api.get("/resources")
    async def resources():
        return monitor.snapshot()

    @api.get("/management/events")
    async def events(limit: int = 50):
        return manager.store.events(max(1, min(limit, 200)))

    @api.post("/run")
    async def run(body: RunBody):
        try:
            agent = router.route(body.action)
        except RouteError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        try:
            output = await agent.run(body.action, body.payload)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except ProviderError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return TaskResult(agent.name, body.action, True, output).to_dict()

    return api
