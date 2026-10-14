"""Rotas HTTP do núcleo."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.models import ProviderError, RouteError, TaskResult
from app.core.registry import AgentRegistry
from app.core.router import ActionRouter


class RunBody(BaseModel):
    action: str
    payload: dict = Field(default_factory=dict)


def build_router(registry: AgentRegistry, router: ActionRouter, provider) -> APIRouter:
    api = APIRouter()

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
                        "description": agent.description,
                        "available": ok, "reason": reason})
        return out

    @api.get("/management/models")
    async def models():
        try:
            return {"provider": provider.name, "installed": await provider.list_models()}
        except ProviderError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

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
