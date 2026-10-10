from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aether.agent.counting import count_python_paths

if TYPE_CHECKING:
    from aether.evidence import EvidenceRecorder
    from aether.indexer import CodebaseIndexer



@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    executed: bool = False
    exit_code: int | None = None
    duration_seconds: float = 0.0
    truncated: bool = False
    data: dict[str, Any] | None = None


class ToolRegistry:
    """Registro de ferramentas que o agente pode chamar."""

    def __init__(self, project_root: Path, indexer: CodebaseIndexer | None = None):
        self.root = project_root.resolve()
        self.indexer = indexer
        self.max_output_chars = 12000
        self.evidence: EvidenceRecorder | None = None
        self.disabled_tools: set[str] = set()
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., Any],
    ) -> None:
        parameters["additionalProperties"] = False
        self._tools[name] = func
        self._schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [s for s in self._schemas if s["function"]["name"] not in self.disabled_tools]

    @property
    def available_tools(self) -> set[str]:
        return set(self._tools) - self.disabled_tools

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if not isinstance(name, str) or name not in self._tools:
            return ToolResult(
                success=False,
                output="",
                error=f"Ferramenta desconhecida: {name}",
            )

        try:
            if not isinstance(arguments, dict):
                raise TypeError("Argumentos devem ser objeto JSON")
            schema = next(s["function"]["parameters"] for s in self._schemas if s["function"]["name"] == name)
            props = schema["properties"]
            if set(arguments) - set(props) or set(schema.get("required", [])) - set(arguments):
                raise ValueError("Argumentos desconhecidos ou obrigatórios ausentes")
            types = {"string": str, "integer": int, "array": list, "boolean": bool}
            for key, value in arguments.items():
                if type(value) is not types[props[key]["type"]]:
                    raise ValueError(f"Tipo inválido: {key}")
                if isinstance(value, list) and any(type(item) is not str for item in value):
                    raise ValueError(f"Array requires string items: {key}")
                if type(value) is int and not (0 if key == "max_depth" else 1) <= value <= (10 if key == "max_depth" else 100 if key == "limit" else 100000):
                    raise ValueError(f"Limite inválido: {key}")
            if name in self.disabled_tools:
                error = f"Ferramenta desabilitada: {name}"
                if name == "run_terminal" and self.evidence:
                    self.evidence.record(
                        artifact=arguments.get("artifact", "."),
                        phase=arguments.get("phase", "verification"),
                        command=arguments["command"], executed=False, exit_code=None,
                        duration_seconds=0, limitations=[error],
                    )
                return ToolResult(False, "", error)
            result = self._tools[name](**arguments)
            if isinstance(result, ToolResult):
                result.truncated = result.truncated or len(result.output) > self.max_output_chars
                result.output = result.output[:self.max_output_chars]
                return result
            text = str(result)
            return ToolResult(success=True, output=text[:self.max_output_chars],
                              truncated=len(text) > self.max_output_chars)
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(success=False, output="", error=str(e))

    def _safe_path(self, path: str) -> Path:
        """Garante que o path fica dentro do projeto."""
        full = (self.root / path).resolve()
        if not full.is_relative_to(self.root):
            raise ValueError(f"Acesso negado fora do projeto: {path}")
        return full


def get_default_tools(
    project_root: Path,
    indexer: CodebaseIndexer | None = None,
    terminal_timeout: int = 30,
    allow_unisolated_terminal: bool = False,
    max_output_chars: int = 12000,
) -> ToolRegistry:
    """Cria o conjunto padrão de ferramentas do Aether."""
    if not 1 <= terminal_timeout <= 120 or max_output_chars < 128:
        raise ValueError("Limites de terminal inválidos")
    registry = ToolRegistry(project_root, indexer)
    registry.max_output_chars = max_output_chars
    if not allow_unisolated_terminal:
        registry.disabled_tools.add("run_terminal")

    def count_python_files(path: str = ".") -> ToolResult:
        registry._safe_path(path)
        report = count_python_paths(registry.root, path)
        return ToolResult(True, json.dumps(report, ensure_ascii=False), data=report)

    registry.register(
        name="count_python_files",
        description="Conta caminhos .py recursivamente, sem ler conteúdo ou contar uma árvore "
                    "textual. Retorna escopo, exclusões e partial/inaccessible_paths. "
                    "Use para perguntas sobre quantidade de arquivos Python.",
        parameters={"type": "object", "properties": {
            "path": {"type": "string", "description": "Diretório relativo", "default": "."},
        }, "required": []},
        func=count_python_files,
    )

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------
    def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> ToolResult:
        try:
            full = registry._safe_path(path)
            if not full.exists():
                return ToolResult(False, "", f"Arquivo não encontrado: {path}")

            if full.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Arquivo excede limite de leitura de 2 MiB")
            text = full.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()

            if end_line is not None and end_line < start_line:
                raise ValueError("Range inválido")
            start = start_line - 1
            end = end_line if end_line else len(lines)
            end = min(end, len(lines))

            selected = lines[start:end]
            numbered = [f"{i+start+1:4d} | {line}" for i, line in enumerate(selected)]
            content = "\n".join(numbered)

            return ToolResult(True, content)
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(False, "", str(e))

    registry.register(
        name="read_file",
        description="Lê o conteúdo de um arquivo. Use start_line e end_line para ler apenas uma parte.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho relativo do arquivo"},
                "start_line": {"type": "integer", "description": "Linha inicial (1-indexed)", "default": 1},
                "end_line": {"type": "integer", "description": "Linha final (opcional)"},
            },
            "required": ["path"],
        },
        func=read_file,
    )

    # ------------------------------------------------------------------
    # write_file
    # ------------------------------------------------------------------
    def write_file(path: str, content: str) -> ToolResult:
        try:
            full = registry._safe_path(path)
            parts = tuple(part.casefold() for part in full.relative_to(registry.root).parts)
            if any(part in {".git", ".agents", ".codex", ".aws"} for part in parts) or parts[:2] in {(".aether", "skills"), (".aether", "evidence")}:
                raise ValueError("Metadados protegidos")
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return ToolResult(True, f"Arquivo escrito com sucesso: {path} ({len(content)} chars)")
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(False, "", str(e))

    registry.register(
        name="write_file",
        description="Escreve (ou sobrescreve) um arquivo completo com o conteúdo fornecido.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho relativo do arquivo"},
                "content": {"type": "string", "description": "Conteúdo completo do arquivo"},
            },
            "required": ["path", "content"],
        },
        func=write_file,
    )

    # ------------------------------------------------------------------
    # list_dir
    # ------------------------------------------------------------------
    def list_dir(path: str = ".") -> ToolResult:
        try:
            full = registry._safe_path(path)
            if not full.exists():
                return ToolResult(False, "", f"Diretório não encontrado: {path}")

            entries = sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = []
            for entry in entries:
                prefix = "📁 " if entry.is_dir() else "📄 "
                lines.append(f"{prefix}{entry.name}")

            return ToolResult(True, "\n".join(lines) if lines else "(vazio)")
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(False, "", str(e))

    registry.register(
        name="list_dir",
        description="Lista arquivos e pastas de um diretório.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho relativo do diretório", "default": "."},
            },
            "required": [],
        },
        func=list_dir,
    )

    # ------------------------------------------------------------------
    # search_codebase (semântico + grep simples)
    # ------------------------------------------------------------------
    def search_codebase(query: str, limit: int = 10) -> ToolResult:
        if not indexer:
            return ToolResult(False, "", "Indexador não disponível. Rode 'aether index' primeiro.")

        try:
            results = indexer.search(query, limit=limit)
            if not results:
                return ToolResult(True, "Nenhum resultado encontrado.")

            parts = []
            for i, r in enumerate(results, 1):
                parts.append(
                    f"[{i}] {r['path']} (linhas {r['start_line']}-{r['end_line']})\n"
                    f"{r['content'][:500]}{'...' if len(r['content']) > 500 else ''}\n"
                )
            return ToolResult(True, "\n".join(parts))
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(False, "", str(e))

    registry.register(
        name="search_codebase",
        description="Busca semântica no codebase indexado. Use para encontrar código relevante por significado.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta em linguagem natural"},
                "limit": {"type": "integer", "description": "Número máximo de resultados", "default": 10},
            },
            "required": ["query"],
        },
        func=search_codebase,
    )

    # ------------------------------------------------------------------
    # run_terminal
    # ------------------------------------------------------------------
    def run_terminal(command: list[str], artifact: str = ".",
                     phase: str = "verification") -> ToolResult:
        registry._safe_path(artifact)
        if phase not in {"before", "after", "verification"}:
            return ToolResult(False, "", "Invalid evidence phase")
        if not allow_unisolated_terminal:
            result = ToolResult(False, "", "Terminal sem isolamento desabilitado por padrão")
        elif not command or any(type(arg) is not str or not arg or "\0" in arg for arg in command):
            result = ToolResult(False, "", "command exige lista não vazia de argumentos")
        else:
            try:
                result = run_process(command)
            except OSError as exc:
                result = ToolResult(False, "", str(exc))
        if registry.evidence:
            registry.evidence.record(artifact=artifact, phase=phase, command=command,
                executed=result.executed, exit_code=result.exit_code,
                duration_seconds=result.duration_seconds, output=result.output,
                limitations=[result.error] if result.error else
                ["Unisolated execution; output may be truncated; direct process only"])
        return result

    registry.register(
        name="run_terminal",
        description="Executa um comando no terminal dentro do diretório do projeto. Use para rodar testes, instalar deps, git, etc.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "description": "Comando a ser executado"},
                "artifact": {"type": "string"},
                "phase": {"type": "string"},
            },
            "required": ["command"],
        },
        func=run_terminal,
    )

    # ------------------------------------------------------------------
    # get_project_structure
    # ------------------------------------------------------------------
    def get_project_structure(max_depth: int = 3) -> ToolResult:
        try:
            lines = []

            def walk(current: Path, prefix: str = "", depth: int = 0) -> None:
                if depth > max_depth or current.is_symlink():
                    return
                try:
                    entries = sorted(
                        [e for e in current.iterdir() if not e.name.startswith(".")],
                        key=lambda p: (not p.is_dir(), p.name.lower()),
                    )
                except PermissionError:
                    return

                for i, entry in enumerate(entries):
                    is_last = i == len(entries) - 1
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{entry.name}")

                    if entry.is_dir() and entry.name not in {
                        "node_modules", "__pycache__", ".venv", "venv",
                        "dist", "build", ".git", "target",
                    }:
                        extension = "    " if is_last else "│   "
                        walk(entry, prefix + extension, depth + 1)

            lines.append(registry.root.name + "/")
            walk(registry.root)
            return ToolResult(True, "\n".join(lines))
        except Exception as e:
            logging.getLogger(__name__).exception("Tool execution failed")
            return ToolResult(False, "", str(e))

    registry.register(
        name="get_project_structure",
        description="Retorna a árvore de arquivos e pastas do projeto.",
        parameters={
            "type": "object",
            "properties": {
                "max_depth": {"type": "integer", "description": "Profundidade máxima", "default": 3},
            },
            "required": [],
        },
        func=get_project_structure,
    )

    def run_process(argv: list[str], env: dict[str, str] | None = None) -> ToolResult:
        import threading
        started = time.perf_counter()
        process = subprocess.Popen(argv, shell=False, cwd=registry.root,
                                   env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        chunks = bytearray()
        def drain() -> None:
            assert process.stdout is not None
            try:
                while block := process.stdout.read(4096):
                    if len(chunks) < max_output_chars * 4:
                        chunks.extend(block[:max_output_chars * 4 - len(chunks)])
            finally:
                process.stdout.close()
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            process.wait(timeout=terminal_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            reader.join(timeout=1)
            return ToolResult(False, "", "Timeout do processo", True, None,
                              time.perf_counter() - started)
        reader.join(timeout=1)
        return ToolResult(process.returncode == 0,
                          chunks.decode("utf-8", errors="replace")[:max_output_chars],
                          executed=True, exit_code=process.returncode,
                          duration_seconds=time.perf_counter() - started)

    def edit_file(path: str, old_text: str, new_text: str) -> ToolResult:
        full = registry._safe_path(path)
        parts = tuple(part.casefold() for part in full.relative_to(registry.root).parts)
        if any(part in {".git", ".agents", ".codex", ".aws"} for part in parts) or parts[:2] in {(".aether", "skills"), (".aether", "evidence")}:
            raise ValueError("Metadados protegidos")
        text = full.read_text(encoding="utf-8")
        if not old_text or text.count(old_text) != 1:
            return ToolResult(False, "", "old_text deve corresponder exatamente uma vez")
        full.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return ToolResult(True, "Arquivo editado")

    registry.register("edit_file", "Substitui trecho único exato", {
        "type": "object", "properties": {k: {"type": "string"} for k in ("path", "old_text", "new_text")},
        "required": ["path", "old_text", "new_text"]}, edit_file)
    def git_read(args: list[str]) -> ToolResult:
        git_dir = registry.root / ".git"
        if not git_dir.is_dir() or git_dir.is_symlink() or not git_dir.resolve().is_relative_to(registry.root):
            return ToolResult(False, "", "Git requires repository metadata inside the project")
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        env["GIT_TERMINAL_PROMPT"] = "0"
        return run_process(["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", *args], env)

    registry.register("git_status", "Status Git local", {"type": "object", "properties": {}},
                      lambda: git_read(["status", "--short"]))
    registry.register("git_diff", "Diff Git sem helpers externos", {"type": "object", "properties": {}},
                      lambda: git_read(["diff", "--no-ext-diff", "--no-textconv"]))

    def record_evidence(artifact: str, reason: str, phase: str = "verification",
                        applicable: bool = True, command: list[str] | None = None) -> ToolResult:
        if registry.evidence is None:
            return ToolResult(False, "", "No active task evidence recorder")
        if not reason.strip():
            return ToolResult(False, "", "Evidence requires a limitation or N/A reason")
        record = registry.evidence.record(artifact=artifact, phase=phase, command=command or [],
            executed=False, exit_code=None, duration_seconds=0,
            limitations=[reason], applicable=applicable)
        return ToolResult(True, f"{record.status}: {reason}")

    registry.register("record_evidence", "Record BLOCKED or N/A; cannot assert PASS", {
        "type": "object", "properties": {
            "artifact": {"type": "string"}, "reason": {"type": "string"},
            "command": {"type": "array", "items": {"type": "string"}},
            "phase": {"type": "string"}, "applicable": {"type": "boolean"}},
        "required": ["artifact", "reason"]}, record_evidence)
    return registry
