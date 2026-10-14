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
from app.core.scheduler import NORMAL, AdmissionError, Job, ResourceScheduler

HEAVY_MB = 200  # a partir daqui o job disputa um slot do ResourceCoordinator


class JobCancelled(SwarmError):
    pass


class JobTimeout(SwarmError):
    pass


class Orchestrator:
    def __init__(self, router: ActionRouter, scheduler: ResourceScheduler, timeout: float = 120.0,
                 coordinator: ResourceCoordinator | None = None, history: int = 100,
                 queue_timeout: float = 60.0) -> None:
        self.router, self.scheduler, self.timeout, self.coordinator = router, scheduler, timeout, coordinator
        self.queue_timeout = queue_timeout
        self._ids = itertools.count(1)
        self._expiry: dict[str, asyncio.TimerHandle] = {}
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
        self._meta[job_id] = {"id": job_id, "agent": agent.name, "model": getattr(agent, "model", ""),
                              "action": action, "priority": priority,
                              "status": "queued", "queued_at": time.time(), "error": ""}
        self._expiry[job_id] = asyncio.get_running_loop().call_later(self.queue_timeout, self._expire, job_id)
        self._pump()
        try:
            return await fut, job_id
        except asyncio.CancelledError:  # cliente desconectou: não deixa job órfão
            self.cancel(job_id)
            raise

    def _expire(self, job_id: str) -> None:
        """Job que ficou tempo demais esperando vaga/RAM: sai da fila com erro, em vez de esperar para sempre."""
        self._expiry.pop(job_id, None)
        if self.scheduler.cancel_queued(job_id):
            meta = self._meta.pop(job_id)
            meta.update(status="timeout", finished_at=time.time(), error="tempo de espera na fila excedido")
            self._history.append(meta)
            fut = self._futures.pop(job_id)
            if not fut.done():
                fut.set_exception(JobTimeout(f"esperou mais de {self.queue_timeout}s na fila (sem vaga ou RAM)"))

    def _pump(self) -> None:
        while (job := self.scheduler.next_runnable()) is not None:
            if timer := self._expiry.pop(job.id, None):
                timer.cancel()
            self._meta[job.id].update(status="running", started_at=time.time())
            self._tasks[job.id] = asyncio.create_task(self._execute(job))

    async def _call(self, agent, job_id: str, action: str, payload: dict, mb: int) -> str:
        """Roda o agente sob timeout e, se pesado, sob um slot do coordenador."""
        slot = None
        try:
            async with asyncio.timeout(self.timeout):
                if self.coordinator and mb >= HEAVY_MB:
                    while (slot := self.coordinator.try_acquire(job_id)) is None:
                        await asyncio.sleep(0.1)
                return await agent.run(action, payload)
        finally:
            if slot:
                slot.release()

    async def run_nested(self, action: str, payload: dict[str, Any]) -> str:
        """Passo de um plano: não toma slot de concorrência (o plano já tem um; evita deadlock),
        mas reserva RAM, respeita timeout e coordenador. Falha rápido se não houver RAM."""
        agent = self.router.route(action)
        mb, owner = self.scheduler.memory.estimate(agent.name), f"nested-{next(self._ids)}"
        if not self.scheduler.memory.try_reserve(owner, mb):
            raise AdmissionError(f"RAM insuficiente agora para {action} (~{mb} MB)")
        try:
            return await self._call(agent, owner, action, payload, mb)
        except TimeoutError:
            raise JobTimeout(f"tempo limite de {self.timeout}s excedido em {action}") from None
        finally:
            self.scheduler.memory.release(owner)

    async def _execute(self, job: Job) -> None:
        fut = self._futures[job.id]
        try:
            agent = self.router.route(job.action)
            result = await self._call(agent, job.id, job.action, job.payload, job.mb)
            self._finish(job, "done", fut, result=result)
        except TimeoutError:
            self._finish(job, "timeout", fut, exc=JobTimeout(f"tempo limite de {self.timeout}s excedido"))
        except asyncio.CancelledError:
            self._finish(job, "cancelled", fut, exc=JobCancelled("job cancelado"))
        except Exception as e:  # erro do agente vai para quem chamou
            self._finish(job, "error", fut, exc=e)

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
            if timer := self._expiry.pop(job_id, None):
                timer.cancel()
            meta = self._meta.pop(job_id)
            meta.update(status="cancelled", finished_at=time.time())
            self._history.append(meta)
            fut = self._futures.pop(job_id)
            if not fut.done():
                fut.set_exception(JobCancelled("job cancelado"))
            return True
        return False

    def snapshot(self) -> dict:
        coord = ({"capacity": self.coordinator.capacity, "in_use": self.coordinator.in_use()}
                 if self.coordinator else None)
        return {**self.scheduler.snapshot(), "timeout": self.timeout, "coordination": coord,
                "jobs": list(self._meta.values()), "recent": list(self._history)[-20:]}
