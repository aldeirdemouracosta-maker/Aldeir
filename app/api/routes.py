"""Rotas HTTP. A lógica fica em core/; aqui só tradução para HTTP."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.manager import AgentManager, ManagerError, ModelManager
from app.core.models import ProviderError, RouteError, SwarmError, TaskResult, UnavailableError
from app.core.resources import ResourceMonitor
from app.core.orchestrator import JobCancelled, JobTimeout, Orchestrator
from app.core.scheduler import PRIORITIES, AdmissionError, QueueFull


class RunBody(BaseModel):
    action: str
    payload: dict = Field(default_factory=dict)
    priority: str = "normal"


class ModelBody(BaseModel):
    model: str


def build_router(manager: AgentManager, orch: Orchestrator, models: ModelManager,
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

    @api.get("/scheduler")
    async def scheduler():
        return orch.snapshot()

    @api.post("/scheduler/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        if not orch.cancel(job_id):
            raise HTTPException(status_code=404, detail=f"job não encontrado: {job_id}")
        return {"job": job_id, "cancelled": True}

    @api.post("/run")
    async def run(body: RunBody):
        if body.priority not in PRIORITIES:
            raise HTTPException(status_code=422, detail="priority deve ser high, normal ou low")
        try:
            output, job_id = await orch.run(body.action, body.payload, PRIORITIES[body.priority])
        except RouteError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except QueueFull as e:
            raise HTTPException(status_code=429, detail=str(e)) from e
        except JobTimeout as e:
            raise HTTPException(status_code=504, detail=str(e)) from e
        except JobCancelled as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except (ProviderError, UnavailableError, AdmissionError) as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except SwarmError as e:  # caminho/mídia inválidos (workspace, assets)
            raise HTTPException(status_code=400, detail=str(e)) from e
        agent = orch.router.route(body.action)
        return {**TaskResult(agent.name, body.action, True, output).to_dict(), "job_id": job_id}

    return api
