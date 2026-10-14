"""ResourceScheduler: fila por prioridade com limites e admissão por memória. Lógica síncrona e pura."""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Any

from app.core.memory import MemoryManager
from app.core.models import SwarmError

HIGH, NORMAL, LOW = 0, 1, 2
PRIORITIES = {"high": HIGH, "normal": NORMAL, "low": LOW}


class QueueFull(SwarmError):
    pass


class AdmissionError(SwarmError):
    pass


@dataclass
class Job:
    id: str
    agent: str
    action: str
    priority: int
    mb: int
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = 0


class ResourceScheduler:
    def __init__(self, memory: MemoryManager, max_concurrent: int = 2, max_queue: int = 16) -> None:
        if max_concurrent < 1 or max_queue < 0:
            raise ValueError("limites inválidos")
        self.memory, self.max_concurrent, self.max_queue = memory, max_concurrent, max_queue
        self._heap: list[tuple[int, int, str]] = []
        self._queued: dict[str, Job] = {}
        self._running: dict[str, Job] = {}
        self._seq = itertools.count()

    def submit(self, job: Job) -> None:
        if not self.memory.could_ever_fit(job.mb):
            raise AdmissionError(f"{job.agent} precisa de ~{job.mb} MB: nunca caberá nesta máquina")
        starts_now = not self._queued and len(self._running) < self.max_concurrent
        if len(self._queued) >= self.max_queue and not starts_now:  # o limite vale para quem espera
            raise QueueFull(f"fila cheia ({self.max_queue})")
        job.seq = next(self._seq)
        self._queued[job.id] = job
        heapq.heappush(self._heap, (job.priority, job.seq, job.id))

    def next_runnable(self) -> Job | None:
        """Melhor job que cabe agora (prioridade, depois ordem de chegada). Reserva a memória.

        Um job grande que não cabe é pulado para não bloquear os menores; isso pode adiar jobs grandes
        enquanto houver jobs pequenos chegando (risco de inanição, documentado)."""
        if len(self._running) >= self.max_concurrent:
            return None
        skipped = []
        chosen = None
        while self._heap:
            item = heapq.heappop(self._heap)
            job = self._queued.get(item[2])
            if job is None:  # cancelado
                continue
            if self.memory.try_reserve(job.id, job.mb):
                chosen = job
                break
            skipped.append(item)
        for item in skipped:
            heapq.heappush(self._heap, item)
        if chosen:
            del self._queued[chosen.id]
            self._running[chosen.id] = chosen
        return chosen

    def finished(self, job_id: str) -> None:
        self._running.pop(job_id, None)
        self.memory.release(job_id)

    def cancel_queued(self, job_id: str) -> bool:
        return self._queued.pop(job_id, None) is not None

    def snapshot(self) -> dict:
        return {"max_concurrent": self.max_concurrent, "max_queue": self.max_queue,
                "queued": [j.id for j in sorted(self._queued.values(), key=lambda j: (j.priority, j.seq))],
                "running": list(self._running), "memory": self.memory.snapshot()}
