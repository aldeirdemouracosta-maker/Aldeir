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


def dispatch(task_type: str, what: str) -> str:
    kind = choose_worker(task_type)
    url = worker_urls().get(kind)
    if url is None:
        return f"[{kind}] {what}"
    req = urllib.request.Request(
        f"{url}/run", data=json.dumps({"task_type": task_type, "what": what}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)["log"]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise WorkerError(f"worker '{kind}' ({url}) falhou: {exc}") from exc
