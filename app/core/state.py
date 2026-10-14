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
                create table if not exists evals(
                    id integer primary key autoincrement, ts real not null, agent text not null,
                    model text not null, suite text not null, passed int not null, total int not null,
                    latency_ms int not null);
                create table if not exists feedback(
                    id integer primary key autoincrement, ts real not null, job_id text not null,
                    agent text not null, model text not null, action text not null, rating int not null);
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

    def add_eval(self, agent: str, model: str, suite: str, passed: int, total: int, latency_ms: int) -> None:
        self._put("insert into evals(ts,agent,model,suite,passed,total,latency_ms) values(?,?,?,?,?,?,?)",
                  (time.time(), agent, model, suite, passed, total, latency_ms))

    def latest_evals(self, agent: str, suite: str) -> list[dict]:
        """Avaliação mais recente de cada modelo, só da suíte atual (suíte mudou = resultado antigo não vale)."""
        with self._lock:
            rows = self._db.execute(
                "select model, passed, total, latency_ms from evals e where agent=? and suite=? and id = "
                "(select max(id) from evals where agent=e.agent and model=e.model and suite=e.suite) "
                "order by model", (agent, suite)).fetchall()
        return [{"model": m, "passed": p, "total": t, "latency_ms": l} for m, p, t, l in rows]

    def add_feedback(self, job_id: str, agent: str, model: str, action: str, rating: int) -> None:
        self._put("insert into feedback(ts,job_id,agent,model,action,rating) values(?,?,?,?,?,?)",
                  (time.time(), job_id, agent, model, action, rating))

    def feedback_summary(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "select agent, model, sum(rating>0), sum(rating<0) from feedback group by agent, model "
                "order by agent, model").fetchall()
        return [{"agent": a, "model": m, "up": u, "down": d} for a, m, u, d in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
