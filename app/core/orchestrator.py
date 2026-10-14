"""Orchestrator: execução controlada (fila, concorrência, timeout, cancelamento, metadados)."""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from typing import Any

from app.core.coordination import ResourceCoordinator
from app.core.models import SwarmError
from app.core.router import ActionRouter
from app.core.scheduler import NORMAL, Job, ResourceScheduler

HEAVY_MB = 200  # a partir daqui o job disputa um slot do ResourceCoordinator


class JobCancelled(SwarmError):
    pass


class JobTimeout(SwarmError):
    pass


class Orchestrator:
    def __init__(self, router: ActionRouter, scheduler: ResourceScheduler, timeout: float = 120.0,
                 coordinator: ResourceCoordinator | None = None, history: int = 100) -> None:
        self.router, self.scheduler, self.timeout, self.coordinator = router, scheduler, timeout, coordinator
        self._ids = itertools.count(1)
        self._futures: dict[str, asyncio.Future] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._meta: dict[str, dict] = {}
        self._history: deque[dict] = deque(maxlen=history)

    async def run(self, action: str, payload: dict[str, Any], priority: int = NORMAL) -> tuple[str, str]:
        """Retorna (saída, job_id). Propaga erros do agente, JobTimeout, JobCancelled, QueueFull, AdmissionError."""
        agent = self.router.route(action)  # RouteError sobe antes de enfileirar
        job_id = f"job-{next(self._ids)}"
        job = Job(job_id, agent.name, action, priority, self.scheduler.memory.estimate(agent.name), payload)
        fut = asyncio.get_running_loop().create_future()
        self.scheduler.submit(job)
        self._futures[job_id] = fut
        self._meta[job_id] = {"id": job_id, "agent": agent.name, "action": action, "priority": priority,
                              "status": "queued", "queued_at": time.time(), "error": ""}
        self._pump()
        try:
            return await fut, job_id
        except asyncio.CancelledError:  # cliente desconectou: não deixa job órfão
            self.cancel(job_id)
            raise

    def _pump(self) -> None:
        while (job := self.scheduler.next_runnable()) is not None:
            self._meta[job.id].update(status="running", started_at=time.time())
            self._tasks[job.id] = asyncio.create_task(self._execute(job))

    async def _execute(self, job: Job) -> None:
        fut, slot = self._futures[job.id], None
        try:
            agent = self.router.route(job.action)
            async with asyncio.timeout(self.timeout):
                if self.coordinator and job.mb >= HEAVY_MB:
                    while (slot := self.coordinator.try_acquire(job.id)) is None:
                        await asyncio.sleep(0.1)
                result = await agent.run(job.action, job.payload)
            self._finish(job, "done", fut, result=result)
        except TimeoutError:
            self._finish(job, "timeout", fut, exc=JobTimeout(f"tempo limite de {self.timeout}s excedido"))
        except asyncio.CancelledError:
            self._finish(job, "cancelled", fut, exc=JobCancelled("job cancelado"))
        except Exception as e:  # erro do agente vai para quem chamou
            self._finish(job, "error", fut, exc=e)
        finally:
            if slot:
                slot.release()

    def _finish(self, job: Job, status: str, fut: asyncio.Future, result=None, exc=None) -> None:
        meta = self._meta.pop(job.id)
        meta.update(status=status, finished_at=time.time(), error=str(exc) if exc else "")
        self._history.append(meta)
        self._tasks.pop(job.id, None)
        self._futures.pop(job.id, None)
        self.scheduler.finished(job.id)
        if not fut.done():
            fut.set_exception(exc) if exc else fut.set_result(result)
        self._pump()

    def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task:
            task.cancel()
            return True
        if self.scheduler.cancel_queued(job_id):
            meta = self._meta.pop(job_id)
            meta.update(status="cancelled", finished_at=time.time())
            self._history.append(meta)
            fut = self._futures.pop(job_id)
            if not fut.done():
                fut.set_exception(JobCancelled("job cancelado"))
            return True
        return False

    def snapshot(self) -> dict:
        return {**self.scheduler.snapshot(), "timeout": self.timeout,
                "jobs": list(self._meta.values()), "recent": list(self._history)[-20:]}
