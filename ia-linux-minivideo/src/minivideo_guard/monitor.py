"""Laço do Safety Guard: coleta → decisão → ação, com log JSONL por job."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from .actions import ActionDispatcher
from .policy import GuardPolicy, Decision
from .sensors import GpuDevice, Reading, SensorBackend, empty_metrics


class JobLog:
    """Um arquivo ``<job_id>.guard.jsonl`` por job; uma linha por registro."""

    def __init__(self, log_dir: str, job_id: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", job_id):
            raise ValueError("job_id deve conter apenas letras, números, '.', '_' ou '-'")
        os.makedirs(log_dir, exist_ok=True)
        self.job_id = job_id
        self.path = os.path.join(log_dir, f"{job_id}.guard.jsonl")

    def write(self, kind: str, **data) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "job_id": self.job_id, "tipo": kind}
        record.update(data)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class GuardMonitor:
    def __init__(self, backend: SensorBackend, device: GpuDevice, policy: GuardPolicy,
                 dispatcher: Optional[ActionDispatcher] = None, log: Optional[JobLog] = None,
                 interval: float = 2.0):
        self.backend = backend
        self.device = device
        self.policy = policy
        self.dispatcher = dispatcher
        self.log = log
        self.interval = interval

    def _safe_read(self) -> Reading:
        try:
            return self.backend.read(self.device)
        except Exception as exc:  # sensor falhou: tudo indisponível, nunca valor inventado
            return Reading(self.device.id, self.backend.name, time.time(), empty_metrics(),
                           [f"falha de leitura: {exc!r}"])

    def step(self) -> Dict:
        reading = self._safe_read()
        decision: Decision = self.policy.evaluate(reading)
        events = self.dispatcher.apply(decision) if self.dispatcher else []
        if self.log:
            self.log.write("amostra", leitura=reading.to_dict(), decisao=decision.to_dict())
            if decision.changed:
                self.log.write("transicao", **decision.to_dict())
            for ev in events:
                self.log.write("acao", **ev)
        return {"leitura": reading, "decisao": decision, "eventos": events}

    def run(self, keep_going: Callable[[], bool], max_samples: Optional[int] = None,
            on_step: Optional[Callable[[Dict], None]] = None) -> int:
        n = 0
        while keep_going() and (max_samples is None or n < max_samples):
            result = self.step()
            n += 1
            if on_step:
                on_step(result)
            if self.dispatcher and self.dispatcher.stopped:
                break
            if max_samples is not None and n >= max_samples:
                break
            time.sleep(self.interval)
        return n
