"""StateGraph do CineForja (Fase 1: nós simulados)."""
from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from ..workers import mock
from .state import MAX_ATTEMPTS, MIN_CONSISTENCY, ProjectState, Shot, dump, next_pending, shots

# Pontos de aprovação humana (ver hitl.py)
INTERRUPT_BEFORE = ["asset_designer", "audio_designer", "editor"]


def director(state: ProjectState) -> dict:
    plan = f"Plano ({state['style']}): {state['brief']}"
    return {"plan": plan, "logs": [mock.run("llm", "Director definiu o plano")]}


def script_writer(state: ProjectState) -> dict:
    board = [Shot(index=i, prompt=f"Shot {i}: {state['brief']}") for i in range(3)]
    return {"storyboard": dump(board), "logs": [mock.run("llm", "ScriptWriter gerou storyboard de 3 shots")]}


def asset_designer(state: ProjectState) -> dict:
    return {"assets": {"characters": ["ref_personagem.png"], "scenes": ["ref_cenario.png"]},
            "logs": [mock.run("heavy_image", "AssetDesigner criou referências")]}


def animator(state: ProjectState) -> dict:
    shot = next_pending(state)
    shot.attempts += 1
    shot.frames_path = f"data/projects/{state['project_id']}/shot_{shot.index}"
    board = [shot if s.index == shot.index else s for s in shots(state)]
    return {"storyboard": dump(board),
            "logs": [mock.run("video", f"Animator shot {shot.index} (tentativa {shot.attempts})")]}


def consistency_checker(state: ProjectState) -> dict:
    # O shot em avaliação é o pending com mais tentativas (acabou de ser animado).
    shot = max((s for s in shots(state) if s.status == "pending"), key=lambda s: s.attempts)
    shot.score = mock.score_shot(shot.index, shot.attempts)
    ok = shot.score >= MIN_CONSISTENCY or shot.attempts >= MAX_ATTEMPTS
    if ok:
        shot.status = "done"
    board = [shot if s.index == shot.index else s for s in shots(state)]
    verdict = "aprovado" if ok else "regenerar"
    return {"storyboard": dump(board),
            "logs": [mock.run("consistency", f"shot {shot.index} score={shot.score:.2f} -> {verdict}")]}


def audio_designer(state: ProjectState) -> dict:
    return {"audio": {"sfx": "sfx.wav", "ambient": "ambient.wav", "music": "trilha.wav"},
            "logs": [mock.run("audio", "AudioDesigner gerou áudio")]}


def editor(state: ProjectState) -> dict:
    out = f"data/projects/{state['project_id']}/final.mp4"
    return {"output_path": out, "logs": [mock.run("cpu", f"Editor exportou {out}")]}


def after_checker(state: ProjectState) -> str:
    return "animator" if next_pending(state) else "audio_designer"


def build_workflow() -> StateGraph:
    g = StateGraph(ProjectState)
    for name, fn in [("director", director), ("script_writer", script_writer),
                     ("asset_designer", asset_designer), ("animator", animator),
                     ("consistency_checker", consistency_checker),
                     ("audio_designer", audio_designer), ("editor", editor)]:
        g.add_node(name, fn)
    g.add_edge(START, "director")
    g.add_edge("director", "script_writer")
    g.add_edge("script_writer", "asset_designer")
    g.add_edge("asset_designer", "animator")
    g.add_edge("animator", "consistency_checker")
    g.add_conditional_edges("consistency_checker", after_checker,
                            {"animator": "animator", "audio_designer": "audio_designer"})
    g.add_edge("audio_designer", "editor")
    g.add_edge("editor", END)
    return g


def build_app(db_path: str = "data/cineforja.db", interrupt_before: list[str] | None = None):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_workflow().compile(
        checkpointer=checkpointer,
        interrupt_before=INTERRUPT_BEFORE if interrupt_before is None else interrupt_before,
    )
