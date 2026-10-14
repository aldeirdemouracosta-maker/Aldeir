"""CLI: swarm agents | run | serve."""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from app.config import Settings
from app.core.models import ProviderError, RouteError, SwarmError
from app.core.router import ActionRouter
from app.main import build_provider, build_registry

app = typer.Typer(help="SWARM LITE AI", no_args_is_help=True)
console = Console()


def _runtime():
    settings = Settings.from_env()
    provider = build_provider(settings)
    registry = build_registry(settings, provider)
    return settings, provider, registry


@app.command()
def agents() -> None:
    """Lista agentes e disponibilidade real."""
    _, _, registry = _runtime()
    table = Table("agente", "ações", "disponível", "motivo")
    for name in registry.names():
        a = registry.get(name)
        ok, why = asyncio.run(a.available())
        table.add_row(name, ", ".join(a.actions), "sim" if ok else "não", why)
    console.print(table)


@app.command()
def run(action: str, text: str = "", path: str = "") -> None:
    """Executa uma ação, ex.: swarm run summarize "texto"; mídia: swarm run image_describe --path foto.png."""
    _, _, registry = _runtime()
    try:
        agent = ActionRouter(registry).route(action)
        console.print(asyncio.run(agent.run(action, {"text": text, "path": path})))
    except (SwarmError, ValueError) as e:
        console.print(f"[red]erro:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def terminal(root: str = ".", model: str = "") -> None:
    """Coding Terminal supervisionado no diretório ROOT."""
    from app.config import load_agent_config
    from app.terminal.memory import SessionMemory
    from app.terminal.ui import Terminal
    from app.terminal.workspace import Workspace

    settings, provider, _ = _runtime()
    model = model or load_agent_config(settings.agents_file).get("coder", {}).get("model", "")
    ws = Workspace(root)
    term = Terminal(ws, provider, model, SessionMemory(db_path=ws.root / ".swarm" / "session.db"),
                    confirm=lambda q: typer.confirm(q, default=False))
    console.print(f"Workspace: {ws.root}  (/help)")
    while True:
        try:
            line = console.input("[bold]swarm>[/bold] ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == "/quit":
            break
        if line.strip():
            console.print(asyncio.run(term.handle(line)), markup=False, highlight=False)


@app.command()
def serve(port: int = 8000) -> None:
    """Sobe a API em 127.0.0.1."""
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
