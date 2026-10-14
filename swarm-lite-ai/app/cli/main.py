"""CLI: swarm agents | run | serve."""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from app.config import Settings
from app.core.models import ProviderError, RouteError
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
def run(action: str, text: str) -> None:
    """Executa uma ação, ex.: swarm run summarize "texto"."""
    _, _, registry = _runtime()
    try:
        agent = ActionRouter(registry).route(action)
        console.print(asyncio.run(agent.run(action, {"text": text})))
    except (RouteError, ProviderError, ValueError) as e:
        console.print(f"[red]erro:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def serve(port: int = 8000) -> None:
    """Sobe a API em 127.0.0.1."""
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
