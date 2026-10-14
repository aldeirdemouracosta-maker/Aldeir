"""MemoryManager: reservas e estimativas de RAM para admissão. Não guarda conversas."""
from __future__ import annotations

from typing import Callable

import psutil

# Estimativas aproximadas (MB) por agente; ajustáveis. Chat/Coder usam o Ollama (processo externo).
DEFAULT_ESTIMATES_MB = {"chat": 64, "coder": 64, "rag": 128, "vision": 1500, "speech": 500, "voice": 600,
                        "ocr": 300, "langid": 0, "planner": 64, "retrieval": 900}


def _available_mb() -> int:
    return psutil.virtual_memory().available // 2**20


def _total_mb() -> int:
    return psutil.virtual_memory().total // 2**20


class MemoryManager:
    def __init__(self, headroom_mb: int = 1024, estimates: dict[str, int] | None = None,
                 available: Callable[[], int] = _available_mb, total: Callable[[], int] = _total_mb) -> None:
        self.headroom_mb = headroom_mb
        self.estimates = {**DEFAULT_ESTIMATES_MB, **(estimates or {})}
        self._available, self._total = available, total
        self._reserved: dict[str, int] = {}

    def estimate(self, agent: str) -> int:
        return self.estimates.get(agent, 0)

    def reserved_mb(self) -> int:
        return sum(self._reserved.values())

    def could_ever_fit(self, mb: int) -> bool:
        return mb <= self._total() - self.headroom_mb

    def try_reserve(self, owner: str, mb: int) -> bool:
        if owner in self._reserved:
            raise ValueError(f"reserva duplicada: {owner}")
        if mb > self._available() - self.headroom_mb - self.reserved_mb():
            return False
        self._reserved[owner] = mb
        return True

    def release(self, owner: str) -> None:
        self._reserved.pop(owner, None)

    def snapshot(self) -> dict:
        return {"available_mb": self._available(), "headroom_mb": self.headroom_mb,
                "reserved_mb": self.reserved_mb(), "reservations": dict(self._reserved)}
