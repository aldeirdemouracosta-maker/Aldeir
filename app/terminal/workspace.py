"""Workspace: acesso de leitura restrito a uma raiz. Bloqueia traversal, symlinks e hardlinks."""
from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.models import SwarmError

IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".swarm", "build", ".gradle", "dist"}


class WorkspaceError(SwarmError):
    pass


class Workspace:
    def __init__(self, root: str | Path, max_file_bytes: int = 512_000) -> None:
        self.root = Path(root).resolve()
        self.max_file_bytes = max_file_bytes

    def resolve(self, rel: str, must_exist: bool = True) -> Path:
        """Converte caminho relativo em absoluto seguro dentro da raiz."""
        if not rel or "\x00" in rel or Path(rel).is_absolute() or re.match(r"^[A-Za-z]:", rel):
            raise WorkspaceError(f"caminho inválido: {rel!r}")
        lexical = self.root / rel
        # symlink em qualquer componente existente é recusado (inclusive dentro da raiz)
        probe = self.root
        for part in Path(rel).parts:
            probe = probe / part
            if probe.is_symlink():
                raise WorkspaceError(f"symlink não permitido: {rel}")
        target = lexical.resolve()
        if target != self.root and self.root not in target.parents:
            raise WorkspaceError(f"fora do workspace: {rel}")
        if must_exist and not target.exists():
            raise WorkspaceError(f"não existe: {rel}")
        if target.is_file() and target.stat().st_nlink > 1:
            raise WorkspaceError(f"hardlink não permitido: {rel}")
        return target

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def read(self, rel: str) -> str:
        path = self.resolve(rel)
        if not path.is_file():
            raise WorkspaceError(f"não é arquivo: {rel}")
        if path.stat().st_size > self.max_file_bytes:
            raise WorkspaceError(f"arquivo acima do limite de {self.max_file_bytes} bytes: {rel}")
        data = path.read_bytes()
        if b"\x00" in data:
            raise WorkspaceError(f"arquivo binário: {rel}")
        return data.decode("utf-8", errors="replace")

    def files(self):
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in IGNORED_DIRS and not (Path(dirpath) / d).is_symlink())
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if not p.is_symlink():
                    yield p

    def search(self, pattern: str, max_results: int = 50) -> list[tuple[str, int, str]]:
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))
        out: list[tuple[str, int, str]] = []
        for p in self.files():
            try:
                if p.stat().st_size > self.max_file_bytes or p.stat().st_nlink > 1:
                    continue
                text = p.read_bytes()
                if b"\x00" in text:
                    continue
                for n, line in enumerate(text.decode("utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        out.append((self.rel(p), n, line.strip()[:200]))
                        if len(out) >= max_results:
                            return out
            except OSError:
                continue
        return out

    def tree(self, max_depth: int = 3, max_entries: int = 200) -> str:
        lines: list[str] = []

        def walk(d: Path, depth: int) -> None:
            if depth > max_depth or len(lines) >= max_entries:
                return
            for child in sorted(d.iterdir(), key=lambda c: (c.is_file(), c.name)):
                if len(lines) >= max_entries:
                    lines.append("… (truncado)")
                    return
                if child.is_symlink() or child.name in IGNORED_DIRS:
                    continue
                lines.append("  " * depth + child.name + ("/" if child.is_dir() else ""))
                if child.is_dir():
                    walk(child, depth + 1)

        walk(self.root, 0)
        return "\n".join(lines)
