"""ResourceCoordinator: capacidade compartilhada entre processos cooperativos (N slots em disco).

O lease (ttl) precisa ser maior que o timeout dos jobs, senão outro processo pode tomar o slot em uso."""
from __future__ import annotations

import os
from pathlib import Path

from app.core.locking import try_create


class Slot:
    def __init__(self, path: Path) -> None:
        self.path = path

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


class ResourceCoordinator:
    def __init__(self, directory: Path, capacity: int = 1, ttl: float = 300.0) -> None:
        if capacity < 1:
            raise ValueError("capacidade deve ser >= 1")
        self.dir, self.capacity, self.ttl = Path(directory), capacity, ttl

    def try_acquire(self, owner: str) -> Slot | None:
        for i in range(self.capacity):
            p = self.dir / f"slot-{i}.lease"
            if try_create(p, f"{owner}:{os.getpid()}", self.ttl):
                return Slot(p)
        return None

    def in_use(self) -> int:
        return sum(1 for i in range(self.capacity) if (self.dir / f"slot-{i}.lease").exists())
