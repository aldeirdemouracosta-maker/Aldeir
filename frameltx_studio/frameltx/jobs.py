"""Fila de gerações.

Uma única thread de trabalho processa os pedidos em ordem (a GPU só aguenta um
vídeo por vez). A interface apenas consulta o estado do job, então ela nunca
trava — o usuário pode enfileirar várias gerações e acompanhar cada uma.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from PIL import Image

from .backends import Backend
from .comfy_client import ComfyError
from .config import AppConfig
from .pipelines import CancelledError, GenerationRequest, PipelineContext, UserFacingError, run_generation
from .storage import HistoryEntry, Storage
from .vram import QualityProfile

log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "na fila"
    RUNNING = "gerando"
    DONE = "concluído"
    FAILED = "falhou"
    CANCELLED = "cancelado"


@dataclass
class Job:
    request: GenerationRequest
    profile: QualityProfile
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = "Aguardando na fila…"
    preview: Image.Image | None = None
    logs: list[str] = field(default_factory=list)
    result: HistoryEntry | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    cancel_requested: bool = False

    @property
    def finished(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)

    def log(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{stamp}] {line}")
        del self.logs[:-200]  # mantém só as últimas linhas


class JobManager:
    def __init__(self, backend: Backend, storage: Storage, cfg: AppConfig) -> None:
        self.backend = backend
        self.storage = storage
        self.cfg = cfg
        self._queue: queue.Queue[Job] = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._current: Job | None = None
        self._worker = threading.Thread(target=self._loop, name="frameltx-worker", daemon=True)
        self._worker.start()

    # ---------- API usada pela interface ----------
    def submit(self, request: GenerationRequest, profile: QualityProfile) -> Job:
        job = Job(request=request, profile=profile)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        job.log(f"Pedido recebido: {request.mode}, {request.duration_s}s, perfil {profile.label}")
        self._queue.put(job)
        log.info("Job %s enfileirado (posição %d)", job.id, self.position(job.id))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def position(self, job_id: str) -> int:
        """Posição na fila (0 = executando agora ou finalizado)."""
        with self._lock:
            waiting = [j for j in self._order if self._jobs[j].status == JobStatus.QUEUED]
        return waiting.index(job_id) + 1 if job_id in waiting else 0

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or job.finished:
            return
        job.cancel_requested = True
        job.log("Cancelamento solicitado…")
        if job is self._current:
            self.backend.interrupt()

    def recent(self, limit: int = 10) -> list[Job]:
        with self._lock:
            return [self._jobs[j] for j in reversed(self._order[-limit:])]

    # ---------- worker ----------
    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            if job.cancel_requested:
                job.status, job.message = JobStatus.CANCELLED, "Cancelado antes de iniciar."
                continue
            self._current = job
            try:
                self._run(job)
            finally:
                self._current = None
                self._queue.task_done()

    def _emit_for(self, job: Job) -> Callable[[float, str, Image.Image | None], None]:
        def emit(frac: float, msg: str, preview: Image.Image | None) -> None:
            if frac >= 0:
                job.progress = max(job.progress, min(frac, 1.0))
                if msg != job.message and "Passo " not in msg:  # passos do sampler só na barra
                    job.log(msg)
                job.message = msg
            else:  # frac < 0 = apenas aviso no log
                job.log(msg)
            if preview is not None:
                job.preview = preview

        return emit

    def _run(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.message = "Iniciando…"
        ctx = PipelineContext(
            backend=self.backend, storage=self.storage, cfg=self.cfg, profile=job.profile,
            emit=self._emit_for(job), is_cancelled=lambda: job.cancel_requested,
        )
        try:
            job.result = run_generation(ctx, job.request)
            job.status, job.progress = JobStatus.DONE, 1.0
            job.message = f"✅ Pronto em {job.result.elapsed_s:.0f}s"
        except CancelledError as exc:
            job.status, job.message = JobStatus.CANCELLED, str(exc)
        except (UserFacingError, ComfyError) as exc:
            if job.cancel_requested:
                job.status, job.message = JobStatus.CANCELLED, "Geração cancelada pelo usuário."
            else:
                job.status, job.error, job.message = JobStatus.FAILED, str(exc), f"❌ {exc}"
        except Exception as exc:  # noqa: BLE001 — o worker nunca pode morrer
            log.error("Erro inesperado no job %s:\n%s", job.id, traceback.format_exc())
            job.status, job.error = JobStatus.FAILED, f"Erro inesperado: {exc}"
            job.message = f"❌ Erro inesperado: {exc} (detalhes no terminal)"
        job.log(job.message)
        log.info("Job %s terminou: %s", job.id, job.status.value)
