"""Locks cooperativos entre processos (portável: criação exclusiva de arquivo + lease com expiração).

Cooperativo: só protege contra quem também usa o lock. Não impede processos alheios.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil

from app.core.models import SwarmError


class LockTimeout(SwarmError):
    pass


def _stale(path: Path, ttl: float) -> bool:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - info["ts"]
        return age > ttl or not psutil.pid_exists(info["pid"])
    except (OSError, ValueError, KeyError):
        # arquivo ilegível: só considera abandonado se for antigo
        try:
            return time.time() - path.stat().st_mtime > ttl
        except OSError:
            return False


def try_create(path: Path, owner: str, ttl: float) -> bool:
    """Tenta criar o lease. Retoma leases abandonados (dono morto ou expirado)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _stale(path, ttl):
                try:
                    path.unlink()
                except OSError:
                    return False
                continue
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "ts": time.time(), "owner": owner}, f)
        return True
    return False


class FileLock:
    def __init__(self, path: Path, owner: str = "swarm", ttl: float = 60.0,
                 timeout: float = 10.0, poll: float = 0.05) -> None:
        self.path, self.owner, self.ttl, self.timeout, self.poll = Path(path), owner, ttl, timeout, poll
        self._held = False

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout
        while not try_create(self.path, self.owner, self.ttl):
            if time.monotonic() >= deadline:
                raise LockTimeout(f"lock ocupado: {self.path.name}")
            time.sleep(self.poll)
        self._held = True

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
