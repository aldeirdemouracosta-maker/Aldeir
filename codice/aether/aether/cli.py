from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from aether.agent import AetherAgent
from aether.agent.tools import get_default_tools
from aether.config import AetherConfig
from aether.indexer.cache import EmbeddingCache
from aether.skills import SkillError, SkillLoader

app = typer.Typer(
    name="aether",
    help="Aether - Local Coding Agent",
    add_completion=False,
)
console = Console()


def load_project_config(root: Path) -> AetherConfig:
    if not root.is_dir():
        raise typer.BadParameter("O projeto deve ser um diretório existente")
    config = AetherConfig.load(root / "aether.yaml")
    config.project_root = root
    return config


@app.command()
def index(
    path: str = typer.Argument(".", help="Caminho do projeto para indexar"),
    force: bool = typer.Option(False, "--force", "-f", help="Reindexar tudo do zero"),
):
    """Indexa o codebase localmente."""
    root = Path(path).resolve()
    if not root.exists():
        console.print(f"[red]Caminho não existe:[/red] {root}")
        raise typer.Exit(1)

    config = load_project_config(root)
    console.print(Panel.fit(
        f"[bold]Aether Indexer[/bold]\nProjeto: {root}",
        border_style="cyan"
    ))

    from aether.indexer.indexer import CodebaseIndexer
    indexer = CodebaseIndexer(config)
    try:
        stats = indexer.index(force=force)
        console.print(stats)
        if indexer.embedder.cache:
            console.print({"cache": indexer.embedder.cache.metrics(),
                           "model_digest": indexer.embedder.digest})
        console.print(f"\n[bold green]Pronto![/bold green] Total de chunks no índice: {indexer.store.count()}")
    finally:
        indexer.close()


@app.command()
def search(
    query: str = typer.Argument(..., help="Consulta semântica"),
    path: str = typer.Option(".", "--path", "-p", help="Caminho do projeto"),
    limit: int = typer.Option(8, "--limit", "-n", help="Número de resultados", min=1, max=100),
):
    """Busca semântica no codebase indexado."""
    root = Path(path).resolve()
    config = load_project_config(root)
    from aether.indexer.indexer import CodebaseIndexer
    indexer = CodebaseIndexer(config)

    try:
        results = indexer.search(query, limit=limit)
    finally:
        indexer.close()

    if not results:
        console.print("[yellow]Nenhum resultado encontrado. Rode 'aether index' primeiro.[/yellow]")
        return

    console.print(f"\n[bold]Resultados para:[/bold] [cyan]{query}[/cyan]\n")

    for i, r in enumerate(results, 1):
        header = f"[bold]{i}. {r['path']}[/bold] (linhas {r['start_line']}-{r['end_line']})"
        console.print(header)
        console.print(Panel(
            r["content"][:600] + ("..." if len(r["content"]) > 600 else ""),
            border_style="dim",
            expand=False,
        ))
        console.print()


@app.command()
def status(
    path: str = typer.Argument(".", help="Caminho do projeto"),
):
    """Mostra status do índice."""
    root = Path(path).resolve()
    config = load_project_config(root)
    from aether.indexer.indexer import CodebaseIndexer
    indexer = CodebaseIndexer(config)

    count = indexer.store.count()
    paths = indexer.store.get_indexed_paths()
    indexer.close()

    console.print(Panel.fit(
        f"[bold]Status do Índice[/bold]\n"
        f"Projeto: {root}\n"
        f"Chunks: {count}\n"
        f"Arquivos indexados: {len(paths)}",
        border_style="green"
    ))


@app.command()
def run(
    task: str = typer.Argument(..., help="Tarefa que o agente deve executar"),
    path: str = typer.Option(".", "--path", "-p", help="Caminho do projeto"),
    skill: Annotated[list[str] | None, typer.Option("--skill", help="Skill local explícita; repetível")] = None,
):
    """Executa o agente de código em uma tarefa."""
    root = Path(path).resolve()
    if not root.exists():
        console.print(f"[red]Caminho não existe:[/red] {root}")
        raise typer.Exit(1)

    config = load_project_config(root)
    agent = AetherAgent(config, ask_user=lambda question: console.input(question + "\n> "))

    try:
        result = agent.run(task, skills=skill)
    finally:
        agent.close()
    if agent.last_evidence:
        console.print(agent.last_evidence.summary(), markup=False)
    console.print()
    console.print(Panel(
        Markdown(result) if result else "(sem saída)",
        title="Resultado Final",
        border_style="bold green",
    ))


@app.command()
def chat(
    path: str = typer.Option(".", "--path", "-p", help="Caminho do projeto"),
):
    """Modo interativo de chat com o agente."""
    root = Path(path).resolve()
    config = load_project_config(root)
    agent = AetherAgent(config, ask_user=lambda question: console.input(question + "\n> "))
    selected: list[str] = []

    console.print(Panel.fit(
        "[bold]Aether Chat[/bold]\nDigite sua tarefa ou 'sair' para terminar.",
        border_style="cyan",
    ))

    while True:
        try:
            user_input = console.input("\n[bold cyan]você>[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Até mais![/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in {"sair", "exit", "quit", "q"}:
            console.print("[dim]Até mais![/dim]")
            break

        if user_input == "/skills":
            for metadata in agent.skill_loader.discover():
                console.print(f"{metadata.name}: {metadata.description}", markup=False)
            console.print(agent.skill_loader.errors, markup=False)
            continue
        if user_input.startswith("/skill "):
            names = user_input[7:].split()
            if names == ["clear"]:
                selected = []
            else:
                try:
                    for name in names:
                        agent.skill_loader.load(name, agent.tools.available_tools)
                    selected = names
                except (SkillError, OSError) as exc:
                    console.print(str(exc), markup=False)
                    continue
            console.print({"selected_skills": selected})
            continue

        result = agent.run(user_input, skills=selected)
        if agent.last_evidence:
            console.print(agent.last_evidence.summary(), markup=False)
        console.print()
        console.print(Panel(
            Markdown(result) if result else "(sem saída)",
            title="Aether",
            border_style="green",
        ))


    agent.close()


@app.command("skills")
def skills_list(path: str = typer.Option(".", "--path", "-p")) -> None:
    config = load_project_config(Path(path).resolve())
    loader = SkillLoader(config.project_root, max_bytes=config.skills.max_bytes,
                         max_skills=config.skills.max_skills)
    for metadata in loader.discover():
        console.print(f"{metadata.name}: {metadata.description}", markup=False)
    for name, error in loader.errors.items():
        console.print(f"BLOCKED {name}: {error}", markup=False)


@app.command("skill-show")
def skill_show(name: str, path: str = typer.Option(".", "--path", "-p")) -> None:
    config = load_project_config(Path(path).resolve())
    tools = get_default_tools(config.project_root,
        allow_unisolated_terminal=config.agent.allow_unisolated_terminal)
    try:
        skill = SkillLoader(config.project_root).load(name, tools.available_tools)
    except (SkillError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"{skill.metadata.name} v{skill.version}\n{skill.instructions}", markup=False)


def open_cache(config: AetherConfig) -> EmbeddingCache:
    path = (config.project_root / config.cache.path).resolve()
    if not path.is_relative_to(config.project_root.resolve()):
        raise typer.BadParameter("Embedding cache outside project")
    return EmbeddingCache(path, max_bytes=config.cache.max_bytes)


@app.command("cache-status")
def cache_status(path: str = typer.Option(".", "--path", "-p")) -> None:
    cache = open_cache(load_project_config(Path(path).resolve()))
    try:
        console.print(cache.metrics())
    finally:
        cache.close()


@app.command("cache-clear")
def cache_clear(path: str = typer.Option(".", "--path", "-p")) -> None:
    cache = open_cache(load_project_config(Path(path).resolve()))
    try:
        console.print({"invalidated": cache.invalidate()})
    finally:
        cache.close()


if __name__ == "__main__":
    app()
