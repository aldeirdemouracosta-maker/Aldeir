"""Deterministic path counting without model interpretation or file-content reads."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".cache",
})
# Only known generated locations at the project root, not arbitrary tmp directories.
EXCLUDED_ROOT_PATHS = frozenset({
    (".buildtmp",), (".tmp",), (".aether", "evidence"),
    (".aether", "lancedb"), (".aether", "gui-install-tmp"),
})


def count_python_paths(root: Path, path: str = ".") -> dict[str, Any]:
    root = root.resolve()
    start = (root / path).resolve()
    if not start.is_relative_to(root):
        raise ValueError("Acesso negado fora do projeto")
    requested = root / path
    if any(candidate.is_symlink() or candidate.is_junction()
           for candidate in (requested, *requested.parents)
           if candidate.is_relative_to(root) and candidate != root):
        raise ValueError("Diretório vinculado não permitido")
    if not start.is_dir():
        raise ValueError("O escopo deve ser um diretório existente")
    report: dict[str, Any] = {
        "count": 0, "scope": str(start.relative_to(root)), "extension": ".py",
        "recursive": True, "partial": False,
        "excluded_directory_names": sorted(EXCLUDED_DIR_NAMES),
        "excluded_root_paths": sorted("/".join(parts) for parts in EXCLUDED_ROOT_PATHS),
        "links_followed": False, "excluded_paths": [], "inaccessible_paths": [],
    }

    def inaccessible(candidate: Path, error: OSError) -> None:
        report["partial"] = True
        report["inaccessible_paths"].append({
            "path": str(candidate.relative_to(root)),
            "error": f"{type(error).__name__}: {error}",
        })

    pending = [start]
    while pending:
        current = pending.pop()
        relative_parts = tuple(part.casefold() for part in current.relative_to(root).parts)
        if (any(part in EXCLUDED_DIR_NAMES for part in relative_parts)
                or any(relative_parts[:len(parts)] == parts for parts in EXCLUDED_ROOT_PATHS)):
            report["excluded_paths"].append({"path": str(current.relative_to(root)),
                                             "reason": "generated_or_cache"})
            continue
        try:
            # Re-check structural confinement before each directory traversal.
            if not current.resolve().is_relative_to(root):
                raise ValueError("Caminho saiu do projeto durante a contagem")
            with os.scandir(current) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
        except OSError as exc:
            inaccessible(current, exc)
            continue
        for entry in children:
            candidate = Path(entry.path)
            relative = candidate.relative_to(root)
            parts = tuple(part.casefold() for part in relative.parts)
            try:
                if candidate.is_symlink() or candidate.is_junction():
                    report["excluded_paths"].append({"path": str(relative), "reason": "link"})
                    continue
                if not candidate.resolve().is_relative_to(root):
                    raise ValueError("Caminho fora do projeto")
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in EXCLUDED_DIR_NAMES or parts in EXCLUDED_ROOT_PATHS:
                        report["excluded_paths"].append({
                            "path": str(relative), "reason": "generated_or_cache",
                        })
                    else:
                        pending.append(candidate)
                elif entry.is_file(follow_symlinks=False) and candidate.suffix.casefold() == ".py":
                    report["count"] += 1
            except OSError as exc:
                inaccessible(candidate, exc)
    report["inaccessible_paths"].sort(key=lambda item: item["path"])
    report["excluded_paths"].sort(key=lambda item: item["path"])
    return report


def is_project_python_count(request: str) -> bool:
    """Recognize only the scoped whole-project count request, not arbitrary tasks."""
    return re.fullmatch(
        r"(?:ol[áa][,!]?\s*)?(?:me diga\s+)?quantos arquivos (?:python|\.py) "
        r"(?:existem|h[áa]) (?:neste|nesse|no) projeto[?.!]?",
        request.strip(), flags=re.IGNORECASE,
    ) is not None


def format_python_count(report: dict[str, Any]) -> str:
    partial = report["partial"]
    lines = [f"{report['count']} arquivos Python (.py). "
             + ("Contagem parcial." if partial else "Contagem completa no escopo definido."),
             f"Escopo: {report['scope']}, recursivo; conta caminhos de arquivos regulares.",
             "Exclusões de diretórios: " + ", ".join(report["excluded_directory_names"]),
             "Exclusões na raiz: " + ", ".join(report["excluded_root_paths"]),
             "Links e junctions não são seguidos. Diretórios tmp legítimos são incluídos."]
    errors = report["inaccessible_paths"]
    if errors:
        lines.append("Caminhos inacessíveis:")
        lines.extend(f"- {item['path']}: {item['error']}" for item in errors[:10])
        if len(errors) > 10:
            lines.append(f"Mais {len(errors) - 10} caminhos inacessíveis nas evidências da tarefa.")
    return "\n".join(lines)
