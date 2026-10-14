"""SessionMemory: histórico curto, resumo e arquivos recentes. Não gerencia RAM."""
from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path


class SessionMemory:
    def __init__(self, max_turns: int = 20, max_files: int = 10, db_path: Path | None = None) -> None:
        self.turns: deque[tuple[str, str]] = deque(maxlen=max_turns)
        self.recent_files: deque[str] = deque(maxlen=max_files)
        self.summary = ""
        self._db = None
        if db_path:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(db_path)
            self._db.execute("create table if not exists session(k text primary key, v text)")
            self._load()

    def add_turn(self, role: str, text: str) -> None:
        self.turns.append((role, text))
        self._save()

    def touch_file(self, rel: str) -> None:
        if rel in self.recent_files:
            self.recent_files.remove(rel)
        self.recent_files.append(rel)
        self._save()

    def set_summary(self, text: str) -> None:
        self.summary = text
        self._save()

    def context(self) -> str:
        parts = [f"Resumo: {self.summary}"] if self.summary else []
        if self.recent_files:
            parts.append("Arquivos recentes: " + ", ".join(self.recent_files))
        parts += [f"{r}: {t}" for r, t in self.turns]
        return "\n".join(parts)

    def _save(self) -> None:
        if self._db:
            blob = json.dumps({"turns": list(self.turns), "files": list(self.recent_files),
                               "summary": self.summary})
            self._db.execute("insert or replace into session values('state', ?)", (blob,))
            self._db.commit()

    def _load(self) -> None:
        row = self._db.execute("select v from session where k='state'").fetchone()
        if row:
            d = json.loads(row[0])
            self.turns.extend(tuple(t) for t in d["turns"])
            self.recent_files.extend(d["files"])
            self.summary = d["summary"]

    def close(self) -> None:
        if self._db:
            self._db.close()
