"""Cliente dos workers. URLs via CINEFORJA_WORKERS="cuda=http://127.0.0.1:8101,vulkan=http://127.0.0.1:8102".

Sem a variável, as tarefas rodam em processo (modo simulado da Fase 1).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .router import choose_worker

TIMEOUT = float(os.environ.get("CINEFORJA_WORKER_TIMEOUT", "900"))


class WorkerError(RuntimeError):
    pass


def worker_urls() -> dict[str, str]:
    raw = os.environ.get("CINEFORJA_WORKERS", "")
    return dict(item.split("=", 1) for item in raw.split(",") if "=" in item)


def call(task_type: str, what: str, payload: dict | None = None) -> dict:
    """Executa a tarefa no worker da GPU certa. Retorna {"log": ..., "result": ... | None}."""
    kind = choose_worker(task_type)
    url = worker_urls().get(kind)
    if url is None:
        return {"log": f"[{kind}] {what}", "result": None}
    req = urllib.request.Request(
        f"{url}/run", data=json.dumps({"task_type": task_type, "what": what, "payload": payload or {}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise WorkerError(f"worker '{kind}' ({url}) recusou a tarefa '{task_type}': {detail}") from exc
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise WorkerError(f"worker '{kind}' ({url}) falhou: {exc}") from exc


def dispatch(task_type: str, what: str) -> str:
    return call(task_type, what)["log"]
