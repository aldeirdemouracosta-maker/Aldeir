"""StateStore: estado dos agentes e eventos (auditoria) em SQLite. Não guarda conversas nem conteúdo."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


class StateStore:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
                create table if not exists agents(name text primary key, state text not null);
                create table if not exists events(
                    id integer primary key autoincrement, ts real not null,
                    kind text not null, data text not null);
            """)

    def _put(self, sql: str, args: tuple) -> None:
        with self._lock, self._db:
            self._db.execute(sql, args)

    def set_agent_state(self, name: str, state: dict) -> None:
        self._put("insert or replace into agents values(?,?)", (name, json.dumps(state)))

    def agent_states(self) -> dict[str, dict]:
        with self._lock:
            rows = self._db.execute("select name, state from agents").fetchall()
        return {n: json.loads(s) for n, s in rows}

    def log_event(self, kind: str, data: dict | None = None) -> None:
        self._put("insert into events(ts, kind, data) values(?,?,?)",
                  (time.time(), kind, json.dumps(data or {})))

    def events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "select ts, kind, data from events order by id desc limit ?", (limit,)).fetchall()
        return [{"ts": t, "kind": k, "data": json.loads(d)} for t, k, d in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
