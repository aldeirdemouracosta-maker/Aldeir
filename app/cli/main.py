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


@app.callback()
def _setup() -> None:
    from app.stdio import utf8_stdio
    utf8_stdio()  # Windows: saída redirecionada em cp1252 quebraria com "→" e acentos raros
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
def run(action: str, text: str = typer.Argument("", help="texto da ação"),
        path: str = typer.Option("", help="arquivo de mídia, relativo a SWARM_MEDIA")) -> None:
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
def tune(agent: str, models: str = typer.Option("", help="candidatos separados por vírgula (padrão: todos os instalados)"),
         apply: bool = typer.Option(False, help="aplica a recomendação (troca o modelo do agente)"),
         evals_dir: str = typer.Option("", help="pasta das suítes (padrão: as do pacote)")) -> None:
    """Avalia modelos candidatos com a suíte do agente e recomenda o melhor. Não altera pesos."""
    from pathlib import Path

    from app.core.tuning import SuiteError, evaluate, load_suite, recommend, record
    from app.main import build_manager

    async def go() -> None:
        settings = Settings.from_env()
        provider = build_provider(settings)
        manager = build_manager(settings, provider)
        spec = manager.factories.get(agent)
        if spec is None:
            raise SuiteError(f"agente desconhecido: {agent}")
        suite = load_suite(agent, Path(evals_dir) if evals_dir else settings.evals_dir)
        current = manager.status()
        current = next(s["model"] for s in current if s["name"] == agent)
        if spec.text_model:
            installed = await provider.list_models()
            wanted = [m.strip() for m in models.split(",") if m.strip()] or installed
            candidates = [m for m in wanted if m in installed]
            for m in set(wanted) - set(candidates):
                console.print(f"[yellow]ignorado (não instalado):[/yellow] {m}")
        else:
            candidates = [""]  # agente sem modelo de texto (ex.: langid): avalia a implementação
        for model in candidates:
            r = await evaluate(spec.build(provider, model), suite, settings.job_timeout)
            record(manager.store, suite, model, r)
            console.print(f"{model or agent}: {r['passed']}/{r['total']} · {r['latency_ms']} ms (mediana)")
            for f in r["fails"]:
                console.print(f"  [red]✗[/red] {f}")
        if not spec.text_model:
            return
        rec = recommend(manager.store.latest_evals(agent, suite.sha), current)
        console.print(f"recomendação: {rec.reason}")
        if rec.model and apply:
            await manager.set_model(agent, rec.model)
            console.print(f"modelo de {agent} trocado para {rec.model}")
        elif rec.model:
            console.print(f"para aplicar: swarm tune {agent} --models {rec.model} --apply")
        await provider.aclose()

    try:
        asyncio.run(go())
    except (SwarmError, ValueError) as e:
        console.print(f"[red]erro:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def chat(session: str = typer.Option("padrao", help="nome da conversa (memória local em ~/.swarm/conversations.db)"),
         clear: bool = typer.Option(False, help="apaga a memória desta sessão e sai")) -> None:
    """Conversa interativa com memória por sessão. Linha vazia ou Ctrl+C sai."""
    from app.core.conversations import ConversationError
    from app.main import build_conversations, build_manager

    settings = Settings.from_env()
    store = build_conversations(settings)
    try:
        if clear:
            console.print(f"{store.clear(session)} mensagem(ns) apagada(s)")
            return
        manager = build_manager(settings, build_provider(settings), conversations=store)
        agent = manager.registry.get("chat")
        console.print(f"sessão [bold]{session}[/bold] · modelo {agent.model} · Enter vazio sai")
        while True:
            try:
                line = console.input("[bold]você>[/bold] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            try:
                console.print(asyncio.run(agent.run("chat", {"text": line, "session": session})), markup=False)
            except (SwarmError, ValueError) as e:
                console.print(f"[red]erro:[/red] {e}")
    except ConversationError as e:
        console.print(f"[red]erro:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def serve(port: int = 8000) -> None:
    """Sobe a API em 127.0.0.1."""
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
