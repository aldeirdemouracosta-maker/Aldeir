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


models_app = typer.Typer(help="Modelos de referência: listar, instalar (arquivo único, com SHA-256) e remover.")
app.add_typer(models_app, name="models")


@models_app.callback(invoke_without_command=True)
def models_list(ctx: typer.Context) -> None:
    """Sem subcomando: lista o manifesto e o que está instalado."""
    if ctx.invoked_subcommand:
        return
    from app.core.model_files import installed_path, load_manifests
    s = Settings.from_env()
    table = Table("id", "agentes", "MB", "licença", "adaptador", "instalado")
    for m in load_manifests(s.models_file).values():
        table.add_row(m.id, ",".join(m.agents), f"{m.size_mb:g}", m.license[:28], m.status,
                      "sim" if installed_path(m, s.models_dir) else "não")
    console.print(table)


@models_app.command("install")
def models_install(model_id: str, sha256: str = typer.Option("", help="SHA-256 da página oficial do arquivo"),
                   allow_large: bool = typer.Option(False, help="autoriza arquivos acima de 1 GB")) -> None:
    from app.core.model_files import ModelFileError, install, load_manifests
    s = Settings.from_env()
    manifests = load_manifests(s.models_file)
    if model_id not in manifests:
        console.print(f"[red]erro:[/red] modelo desconhecido: {model_id}")
        raise typer.Exit(1)
    try:
        console.print(f"instalado em {asyncio.run(install(manifests[model_id], s.models_dir, sha256=sha256 or None, allow_large=allow_large))}")
    except ModelFileError as e:
        console.print(f"[red]erro:[/red] {e}")
        raise typer.Exit(1) from e


@models_app.command("remove")
def models_remove(model_id: str) -> None:
    from app.core.model_files import load_manifests, remove
    s = Settings.from_env()
    m = load_manifests(s.models_file).get(model_id)
    console.print("removido" if m and remove(m, s.models_dir) else "nada para remover")


@app.command()
def status() -> None:
    """Estado do runtime: agentes disponíveis, recursos e provedor."""
    from app.core.resources import ResourceMonitor
    settings, provider, registry = _runtime()
    snap = ResourceMonitor().snapshot()
    ok = [n for n in registry.names() if asyncio.run(registry.get(n).available())[0]]
    console.print(f"provedor: {settings.provider} @ {settings.provider_url}")
    console.print(f"agentes disponíveis: {len(ok)}/{len(registry.names())} ({', '.join(ok) or 'nenhum'})")
    console.print(f"CPU {snap['cpu_percent']}% · RAM livre {snap['ram_available_mb']} MB · GPUs {len(snap['gpus'])}")


@app.command()
def serve(port: int = 8000) -> None:
    """Sobe a API em 127.0.0.1."""
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
