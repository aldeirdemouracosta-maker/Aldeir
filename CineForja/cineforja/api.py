"""API local do CineForja (FastAPI). Escuta apenas em 127.0.0.1 e não tem autenticação.

    python -m cineforja.api --db data/cineforja.db --port 8000
"""
from __future__ import annotations

import argparse
import os
import re
import threading
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config
from .orchestrator.graph import build_app
from .orchestrator.hitl import CHECKPOINT_LABELS, config_for
from .orchestrator.state import Shot, dump, new_state, shots

PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STATIC = os.path.join(os.path.dirname(__file__), "static")


class StartReq(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)
    style: Literal["cgi", "stop_motion"] = "cgi"
    project_id: str | None = None


class ShotIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class StoryboardIn(BaseModel):
    shots: list[ShotIn] = Field(min_length=1, max_length=50)


class RegenIn(BaseModel):
    shots: list[int] = Field(min_length=1)
    prompts: dict[int, str] = {}


def create_app(db_path: str = "data/cineforja.db", interrupt_before: list[str] | None = None) -> FastAPI:
    graph = build_app(db_path, interrupt_before)
    api = FastAPI(title="CineForja")
    api.state.graph = graph  # exposto para testes e integrações
    jobs: dict[str, dict] = {}  # pid -> {"running": bool, "error": str | None}
    jobs_lock = threading.Lock()

    def snapshot(pid: str):
        if not PROJECT_ID.match(pid):
            raise HTTPException(400, "project_id inválido")
        snap = graph.get_state(config_for(pid))
        if not snap.values:
            raise HTTPException(404, "projeto não encontrado")
        return snap

    def launch(pid: str, fn, **info) -> None:
        """Executa fn em segundo plano; no máximo um job por projeto."""
        with jobs_lock:
            if jobs.get(pid, {}).get("running"):
                raise HTTPException(409, "projeto em execução")
            jobs[pid] = {"running": True, "error": None, **info}

        def work() -> None:
            err = None
            try:
                fn()
            except Exception as exc:  # o estado antes da falha continua salvo no checkpoint
                err = f"{type(exc).__name__}: {exc}"
            with jobs_lock:
                jobs[pid] = {"running": False, "error": err}  # 'info' só vale enquanto não há checkpoint

        threading.Thread(target=work, daemon=True).start()

    def describe(pid: str) -> dict:
        if not PROJECT_ID.match(pid):
            raise HTTPException(400, "project_id inválido")
        job = jobs.get(pid, {})
        if job.get("running") and not graph.get_state(config_for(pid)).values:
            # job aceito, mas o primeiro checkpoint ainda não foi gravado
            return {"project_id": pid, "status": "running", "error": None, "waiting_for": None, "label": None,
                    "brief": job.get("brief"), "style": job.get("style"), "plan": None, "storyboard": [],
                    "output_path": None, "logs": []}
        snap = snapshot(pid)
        node = snap.next[0] if snap.next else None
        status = "running" if job.get("running") else "error" if job.get("error") else "paused" if node else "done"
        v = snap.values
        return {"project_id": pid, "status": status, "error": job.get("error"), "waiting_for": node,
                "label": CHECKPOINT_LABELS.get(node) if node else None, "brief": v.get("brief"),
                "style": v.get("style"), "plan": v.get("plan"), "storyboard": v.get("storyboard", []),
                "output_path": v.get("output_path"), "logs": v.get("logs", [])}

    @api.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @api.get("/projects")
    def list_projects():
        ids = {c.config["configurable"]["thread_id"] for c in graph.checkpointer.list(None)}
        return sorted(ids | set(jobs))

    @api.post("/projects", status_code=202)
    def start(req: StartReq):
        pid = req.project_id or uuid.uuid4().hex[:8]
        if not PROJECT_ID.match(pid):
            raise HTTPException(400, "project_id inválido (use letras, números, _ e -)")
        if graph.get_state(config_for(pid)).values:
            raise HTTPException(409, "projeto já existe")
        launch(pid, lambda: graph.invoke(new_state(pid, req.brief, req.style), config_for(pid)),
               brief=req.brief, style=req.style)
        return {"project_id": pid, "status": "running"}

    @api.get("/projects/{pid}")
    def state(pid: str):
        return describe(pid)

    @api.put("/projects/{pid}/storyboard")
    def edit_storyboard(pid: str, body: StoryboardIn):
        """Edita o storyboard (só na pausa 'Aprovar storyboard'); shots novos/alterados voltam a pending."""
        d = describe(pid)
        if d["status"] != "paused" or d["waiting_for"] != "asset_designer":
            raise HTTPException(409, "o storyboard só pode ser editado na aprovação do storyboard")
        board = [Shot(index=i, prompt=s.prompt) for i, s in enumerate(body.shots)]
        graph.update_state(config_for(pid), {"storyboard": dump(board)})
        return describe(pid)

    @api.post("/projects/{pid}/regenerate", status_code=202)
    def regenerate(pid: str, body: RegenIn):
        """Na revisão de frames, refaz shots escolhidos (com prompt novo, se enviado) e volta ao Animator."""
        d = describe(pid)
        if d["status"] != "paused" or d["waiting_for"] != "audio_designer":
            raise HTTPException(409, "regeneração só é possível na revisão de frames")
        board = shots(snapshot(pid).values)
        known = {s.index for s in board}
        if not set(body.shots) <= known:
            raise HTTPException(400, "índice de shot inexistente")
        for s in board:
            if s.index in body.shots:
                s.prompt = body.prompts.get(s.index, s.prompt)
                s.status, s.attempts, s.score, s.frames_path = "pending", 0, None, None
        # as_node faz o grafo seguir as arestas do ConsistencyChecker => volta ao Animator
        graph.update_state(config_for(pid), {"storyboard": dump(board)}, as_node="consistency_checker")
        launch(pid, lambda: graph.invoke(None, config_for(pid)))
        return {"project_id": pid, "status": "running"}

    @api.post("/projects/{pid}/continue", status_code=202)
    def proceed(pid: str):
        d = describe(pid)
        if d["status"] not in ("paused", "error"):
            raise HTTPException(409, f"nada a continuar (status: {d['status']})")
        launch(pid, lambda: graph.invoke(None, config_for(pid)))
        return {"project_id": pid, "status": "running"}

    def serve_file(path: str | None, media_type: str | None = None):
        root = os.path.realpath(config.load().output_dir)
        real = os.path.realpath(path) if path else None
        if not real or os.path.commonpath([root, real]) != root or not os.path.isfile(real):
            raise HTTPException(404, "arquivo não encontrado")
        return FileResponse(real, media_type=media_type)

    @api.get("/projects/{pid}/shots/{index}/media")
    def shot_media(pid: str, index: int):
        for s in snapshot(pid).values.get("storyboard", []):
            if s["index"] == index:
                return serve_file(s.get("frames_path"))
        raise HTTPException(404, "shot não encontrado")

    @api.get("/projects/{pid}/final")
    def final(pid: str):
        return serve_file(snapshot(pid).values.get("output_path"), "video/mp4")

    return api


def main(argv: list[str] | None = None) -> None:
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/cineforja.db")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
