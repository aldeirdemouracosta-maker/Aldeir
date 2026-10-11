"""Human-in-the-Loop: pausa, inspeção, edição de estado e retomada."""
from __future__ import annotations

CHECKPOINT_LABELS = {
    "asset_designer": "Aprovar storyboard",
    "audio_designer": "Revisar frames",
    "editor": "Última chance antes da montagem",
}


def config_for(project_id: str) -> dict:
    return {"configurable": {"thread_id": project_id}}


def pending_checkpoint(app, project_id: str) -> str | None:
    """Nome do nó em que o grafo está pausado (None se terminou)."""
    snap = app.get_state(config_for(project_id))
    return snap.next[0] if snap.next else None


def current_state(app, project_id: str) -> dict:
    return app.get_state(config_for(project_id)).values


def edit_state(app, project_id: str, changes: dict) -> None:
    app.update_state(config_for(project_id), changes)


def resume(app, project_id: str):
    return app.invoke(None, config_for(project_id))
