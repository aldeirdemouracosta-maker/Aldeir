"""Tool output rendered as text, never as model-supplied HTML."""
from nicegui import ui


class ToolCallCard(ui.card):
    def __init__(self, name: str, output: str, *, success: bool = True) -> None:
        super().__init__()
        self.classes("tool-card")
        with self:
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("terminal").classes("aether-icon")
                    ui.label(name).classes("tool-name")
                ui.label("Concluída" if success else "Falhou").classes("status-badge").props(
                    f'data-state={"success" if success else "error"}'
                )
            with ui.expansion("Resultado", value=True).classes("w-full"):
                ui.label(output or "(sem saída)").classes("tool-output")
