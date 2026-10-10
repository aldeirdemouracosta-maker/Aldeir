from collections.abc import Callable
from pathlib import Path
from typing import Any

from nicegui import ui


class Sidebar:
    def __init__(self, root: Path, model: str, skills: list[str],
                 on_reset: Callable[..., Any]) -> None:
        with ui.column().classes("aether-sidebar"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("blur_on", size="30px").classes("aether-icon")
                ui.label("Aether").classes("aether-title")
            ui.label("Seu agente de código local").classes("aether-muted")
            self.reset_button = ui.button(
                "Nova conversa", icon="add", on_click=on_reset
            ).props("outline no-caps").classes("w-full")
            ui.label("Projeto").classes("aether-section")
            ui.label(root.name).classes("font-semibold")
            ui.label(str(root)).classes("aether-muted break-all")
            ui.label("Modelo de código").classes("aether-section")
            ui.label(model).classes("status-badge")
            ui.label("Habilidade da tarefa").classes("aether-section")
            self.skills = ui.select(
                skills, multiple=True, value=[], label="Selecionar skills"
            ).props("outlined use-chips").classes("w-full")
            ui.space()
            ui.label("Terminal desabilitado").classes("status-badge")
            ui.label("Ollama local · sem download de modelos").classes("aether-muted")

    def set_busy(self, busy: bool) -> None:
        self.skills.set_enabled(not busy)
        self.reset_button.set_enabled(not busy)
