from collections.abc import Callable
from concurrent.futures import Future, InvalidStateError
from typing import Any

from nicegui import ui

from .tool_card import ToolCallCard


class ChatPanel:
    def __init__(self, on_send: Callable[..., Any]) -> None:
        self.scroll = ui.scroll_area().classes("aether-chat")
        with self.scroll:
            self.messages = ui.column().classes("aether-messages")
        with self.messages, ui.column().classes("aether-welcome"):
            ui.icon("auto_awesome", size="36px").classes("aether-icon")
            ui.label("Vamos explorar seu projeto.").classes("aether-title")
            ui.label(
                "Converse com seu agente local. Planos e resultados de ferramentas "
                "aparecem aqui durante a execução."
            ).classes("aether-muted")
        with ui.column().classes("aether-composer"):
            self.input = ui.textarea(
                placeholder="Descreva uma tarefa para o Aether…"
            ).props('outlined autogrow rows=2 aria-label="Mensagem para o Aether"').classes(
                "w-full"
            )
            self.input.on("keydown.ctrl.enter", on_send)
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Ctrl + Enter para enviar · execução local").classes("aether-muted")
                self.send_button = ui.button(
                    "Enviar", icon="arrow_upward", on_click=on_send
                ).classes("aether-send")

    def scroll_to_bottom(self) -> None:
        # Let Vue lay out the newly appended elements before measuring scroll height.
        # Async handlers/background tasks may not have a current NiceGUI slot.
        with self.scroll:
            ui.timer(0.05, lambda: self.scroll.scroll_to(percent=1.0), once=True)

    def add_message(self, author: str, content: str) -> None:
        with self.messages, ui.column().classes(
            "message-user" if author == "Você" else "message-agent"
        ):
            ui.label(author).classes("message-author")
            ui.label(content).classes("message-body")
        self.scroll_to_bottom()

    def add_tool(self, name: str, output: str, success: bool) -> None:
        with self.messages:
            ToolCallCard(name, output, success=success)
        self.scroll_to_bottom()

    def ask(self, question: str, answer: Future[str]) -> None:
        with self.messages, ui.column().classes("aether-question"):
            ui.label("O Aether precisa da sua resposta").classes("message-author")
            ui.label(question).classes("message-body")
            field = ui.textarea().props('outlined aria-label="Resposta ao agente"').classes(
                "w-full"
            )

            def respond() -> None:
                value = (field.value or "").strip()
                if value and not answer.done():
                    try:
                        answer.set_result(value)
                    except InvalidStateError:
                        return  # The request expired while the user was submitting it.
                    field.disable()
                    button.disable()

            button = ui.button("Responder", on_click=respond).classes("aether-send")
        self.scroll_to_bottom()

    def set_busy(self, busy: bool) -> None:
        self.input.set_enabled(not busy)
        self.send_button.set_enabled(not busy)

    def clear(self) -> None:
        self.messages.clear()
