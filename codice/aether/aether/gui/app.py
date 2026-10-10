"""Desktop entry point: python -m aether.gui.app [--path PROJECT]."""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from queue import Empty
from weakref import WeakSet

from nicegui import app, run, ui

from aether.agent import AetherAgent
from aether.agent.outcome import TaskOutcome
from aether.config import AetherConfig
from aether.gui.components.chat import ChatPanel
from aether.gui.components.sidebar import Sidebar
from aether.gui.session import AgentSession
from aether.gui.styles import apply_theme

logger = logging.getLogger(__name__)
sessions: WeakSet[AetherGUI] = WeakSet()


class AetherGUI:
    """One conversation per client; synchronous agent work stays off the UI loop."""

    def __init__(self, project_root: str | Path = ".", *, demo: bool = False) -> None:
        self.root = Path(project_root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Diretório de projeto inexistente: {self.root}")
        self.config = AetherConfig.load(self.root / "aether.yaml")
        self.config.project_root = self.root
        # The desktop entry point never enables the unisolated terminal.
        self.config.agent.allow_unisolated_terminal = False
        self.demo = demo
        self.busy = False
        self.closed = False
        self.session = AgentSession(self.config, agent_factory=AetherAgent)
        self.client = ui.context.client

    def build(self) -> None:
        apply_theme()
        from aether.skills import SkillLoader

        loader = SkillLoader(self.root, max_bytes=self.config.skills.max_bytes,
                             max_skills=self.config.skills.max_skills)
        names = [skill.name for skill in loader.discover()]
        with ui.row().classes("aether-shell"):
            self.sidebar = Sidebar(self.root, self.config.llm.model, names, self.reset)
            with ui.column().classes("aether-main"):
                with ui.row().classes("aether-header justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label("Workspace").classes("aether-title")
                        ui.label("Conversa com seu projeto").classes("aether-muted")
                        self.reason = ui.label("").classes("aether-muted")
                        self.reason.set_visibility(False)
                    self.status = ui.label(
                        "Prévia visual" if self.demo else "Pronto"
                    ).classes("status-badge")
                self.chat = ChatPanel(self.send)
        if self.demo:
            self.chat.add_message("Você", "Como o cache de embeddings funciona?")
            self.chat.add_message("Plano", "Ler o módulo de cache e identificar a persistência.")
            self.chat.add_tool("read_file", "Prévia: resultado ilustrativo de uma ferramenta.", True)
            self.chat.add_message(
                "Aether", "Este é o esqueleto visual. Nenhum modelo ou ferramenta foi executado."
            )
            self.chat.set_busy(True)
            self.sidebar.set_busy(True)
        self.timer = ui.timer(0.1, self.drain_events)
        self.client.on_delete(self.disconnect)
        sessions.add(self)

    def drain_events(self) -> None:
        if self.closed:
            return
        while True:
            try:
                kind, payload = self.session.events.get_nowait()
            except Empty:
                return
            if kind == "plan":
                self.chat.add_message("Plano", payload)
            elif kind == "tool":
                name, output, success = payload
                self.chat.add_tool(name, output or "(sem saída)", success)
            elif kind == "question":
                question, answer = payload
                self.status.set_text("Aguardando resposta")
                self.chat.ask(question, answer)

    async def send(self) -> None:
        task = (self.chat.input.value or "").strip()
        if not task or self.busy or self.demo or self.closed:
            return
        if self.session.closed:
            if self.session.running:
                self.chat.add_message("Aether", "A tarefa anterior ainda está encerrando; aguarde.")
                return
            self.session = AgentSession(self.config, agent_factory=AetherAgent)
        self.busy = True
        try:
            self.chat.set_busy(True)
            self.sidebar.set_busy(True)
            self.chat.input.set_value("")
            self.chat.add_message("Você", task)
            self.status.set_text("Executando…")
            self.status.props("data-state=busy")
            skills = list(self.sidebar.skills.value or [])
            result = await run.io_bound(self.session.execute, task, skills)
            if self.closed:
                return
            self.drain_events()
            self.chat.add_message("Aether", result or "Execução interrompida sem resposta.")
            outcome = self.session.agent.last_outcome if self.session.agent else None
            if outcome is None:
                outcome = TaskOutcome("incomplete", "worker_no_result",
                                      "A execução assíncrona terminou sem estado de conclusão.")
            if result is None:
                self.session.close()
                outcome = TaskOutcome("incomplete", "worker_no_result",
                                      "A execução assíncrona foi cancelada ou terminou sem resposta. "
                                      "Uma inferência iniciada pode ainda estar encerrando.")
            self.show_outcome(outcome)
            if self.session.agent and self.session.agent.last_evidence:
                self.chat.add_message("Evidência", self.session.agent.last_evidence.summary())
        except asyncio.CancelledError:
            # Cancellation does not stop an already-running thread. Do not reuse its agent.
            self.session.close()
            if not self.closed:
                self.show_outcome(TaskOutcome("incomplete", "cancelled", "Execução cancelada."))
            raise
        except Exception as exc:
            logger.exception("Desktop task failed")
            if not self.closed:
                self.show_outcome(TaskOutcome("failed", "gui_exception",
                                              f"{type(exc).__name__}: {exc}"))
        finally:
            self.busy = False
            if not self.closed:
                for control in (self.chat.input, self.chat.send_button,
                                self.sidebar.skills, self.sidebar.reset_button):
                    try:
                        control.set_enabled(True)
                    except Exception:
                        logger.exception("Failed to restore a desktop control")

    def show_outcome(self, outcome: TaskOutcome) -> None:
        incomplete = outcome.status != "completed"
        self.status.set_text("Execução incompleta" if incomplete else "Pronto")
        self.status.props(f'data-state={"error" if incomplete else "idle"}')
        self.reason.set_text(f"{outcome.code}: {outcome.reason}" if incomplete else "")
        self.reason.set_visibility(incomplete)
        if incomplete:
            try:
                self.chat.add_message("Motivo da interrupção", f"{outcome.code}: {outcome.reason}")
            except Exception:
                # The header already carries the reason if the message renderer itself fails.
                logger.exception("Failed to render interruption message")

    def reset(self) -> None:
        if self.busy or self.demo or self.closed:
            return
        self.session.reset()
        self.chat.clear()
        self.status.set_text("Pronto")
        self.status.props("data-state=idle")
        self.reason.set_text("")
        self.reason.set_visibility(False)

    def disconnect(self) -> None:
        if self.closed:
            return
        self.closed = True
        sessions.discard(self)
        self.session.close()
        if hasattr(self, "timer"):
            self.timer.deactivate()


def close_sessions() -> None:
    for session in list(sessions):
        session.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aether desktop (NiceGUI)")
    parser.add_argument("--path", type=Path, default=Path.cwd())
    parser.add_argument("--demo", action="store_true", help="Prévia visual sem executar agente")
    parser.add_argument("--browser", action="store_true", help="Abrir no navegador, sem pywebview")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    root = args.path.resolve()
    if not root.is_dir():
        parser.error(f"Diretório inexistente: {root}")

    @ui.page("/")
    def index() -> None:
        AetherGUI(root, demo=args.demo).build()

    app.on_shutdown(close_sessions)
    if args.browser:
        # NiceGUI treats window_size as a request for native mode even if native=False.
        ui.run(title="Aether", host="127.0.0.1", port=args.port, native=False,
               dark=True, reload=False)
    else:
        ui.run(title="Aether", host="127.0.0.1", port=args.port, native=True,
               window_size=(1280, 860), dark=True, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
