"""Estado compartilhado do grafo. Tudo aqui precisa ser serializável (checkpointer)."""
from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

ShotStatus = Literal["pending", "done"]
Style = Literal["cgi", "stop_motion"]

MAX_ATTEMPTS = 3
MIN_CONSISTENCY = 0.7


class Shot(BaseModel):
    index: int
    prompt: str
    status: ShotStatus = "pending"
    attempts: int = 0
    score: float | None = None
    frames_path: str | None = None


class ProjectState(TypedDict, total=False):
    project_id: str
    brief: str
    style: Style
    plan: str
    storyboard: list[dict]  # lista de Shot.model_dump()
    assets: dict
    audio: dict
    output_path: str
    # logs acumulam entre nós (reducer de concatenação)
    logs: Annotated[list[str], operator.add]


def new_state(project_id: str, brief: str, style: Style = "cgi") -> ProjectState:
    return ProjectState(
        project_id=project_id, brief=brief, style=style,
        storyboard=[], assets={}, audio={}, logs=[],
    )


def shots(state: ProjectState) -> list[Shot]:
    return [Shot(**s) for s in state.get("storyboard", [])]


def dump(shot_list: list[Shot]) -> list[dict]:
    return [s.model_dump() for s in shot_list]


def next_pending(state: ProjectState) -> Shot | None:
    return next((s for s in shots(state) if s.status == "pending"), None)
