"""Estado da interface de pastas — sem curses, testável.

A navegação nunca sai da raiz do workspace.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional

from minivideo_agents.workspace import FOLDERS, Workspace

KINDS = {
    "vídeo": (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".ts"),
    "áudio": (".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac"),
    "imagem": (".png", ".jpg", ".jpeg", ".webp", ".bmp"),
    "legenda": (".srt", ".vtt", ".ass"),
    "modelo": (".gguf", ".bin", ".param", ".safetensors"),
    "log": (".jsonl", ".log", ".csv", ".json", ".txt"),
}


def kind_of(name: str, is_dir: bool) -> str:
    if is_dir:
        return "pasta"
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in KINDS.items() if ext in exts), "arquivo")


def human_size(n: Optional[int]) -> str:
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return ""


@dataclass
class Entry:
    name: str
    path: str
    is_dir: bool
    size: Optional[int]

    @property
    def kind(self) -> str:
        return kind_of(self.name, self.is_dir)


class Browser:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.folders = list(FOLDERS)
        self.pane = "pastas"          # "pastas" | "arquivos"
        self.folder_idx = 1           # começa em Midia
        self.cwd = ws.path(self.folders[self.folder_idx])
        self.sel = 0
        self.entries: List[Entry] = []
        self.refresh()

    # ---------- leitura ----------
    def refresh(self) -> None:
        try:
            names = os.listdir(self.cwd)
        except OSError:
            names = []
        entries = []
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(self.cwd, n)
            is_dir = os.path.isdir(p)
            try:
                size = None if is_dir else os.path.getsize(p)
            except OSError:
                size = None
            entries.append(Entry(n, p, is_dir, size))
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        self.entries = entries
        self.sel = min(self.sel, max(len(entries) - 1, 0))

    @property
    def selected(self) -> Optional[Entry]:
        return self.entries[self.sel] if self.pane == "arquivos" and self.entries else None

    @property
    def relative_cwd(self) -> str:
        return os.path.relpath(self.cwd, self.ws.root)

    # ---------- navegação ----------
    def move(self, delta: int) -> None:
        if self.pane == "pastas":
            self.folder_idx = max(0, min(len(self.folders) - 1, self.folder_idx + delta))
            self.cwd = self.ws.path(self.folders[self.folder_idx])
            self.sel = 0
            self.refresh()
        elif self.entries:
            self.sel = max(0, min(len(self.entries) - 1, self.sel + delta))

    def toggle_pane(self) -> None:
        self.pane = "arquivos" if self.pane == "pastas" else "pastas"

    def enter(self) -> Optional[Entry]:
        """Entra na pasta; para arquivo, devolve a entrada (a tela decide o que fazer)."""
        if self.pane == "pastas":
            self.pane = "arquivos"
            return None
        e = self.selected
        if e and e.is_dir:
            self.cwd, self.sel = e.path, 0
            self.refresh()
            return None
        return e

    def back(self) -> None:
        top = self.ws.path(self.folders[self.folder_idx])
        if os.path.realpath(self.cwd) == os.path.realpath(top):
            self.pane = "pastas"
            return
        parent = os.path.dirname(self.cwd)
        name = os.path.basename(self.cwd)
        self.cwd = parent
        self.refresh()
        self.sel = next((i for i, e in enumerate(self.entries) if e.name == name), 0)

    def new_folder(self, name: str) -> str:
        name = name.strip()
        if not re.fullmatch(r"[\w .()-]{1,80}", name) or name in (".", ".."):
            raise ValueError("nome inválido: use letras, números, espaço, '.', '-', '_' ou parênteses")
        path = os.path.join(self.cwd, name)
        if os.path.exists(path):
            raise ValueError("já existe um item com esse nome")
        os.makedirs(path)
        self.refresh()
        self.sel = next((i for i, e in enumerate(self.entries) if e.name == name), 0)
        return path

    def default_output(self, entrada: str) -> str:
        stem = os.path.splitext(os.path.basename(entrada))[0]
        base = os.path.join(self.ws.path("Saidas"), f"{stem}_editado")
        out, i = base + ".mp4", 2
        while os.path.exists(out):
            out, i = f"{base}_{i}.mp4", i + 1
        return out
