"""Ações do Safety Guard sobre o JOB — nunca sobre o hardware.

As ações se limitam a pedir ao motor menos carga, pausar, retomar ou
encerrar o processo do job. Não há escrita em sysfs, clocks, voltagens,
ventoinha ou firmware.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Callable, Dict, List, Optional

from .policy import CRITICO, PAUSAR, REDUZIR, Decision


class JobControl:
    """Contrato que um job/motor implementa. Métodos padrão: não suportado."""

    def reduce_load(self) -> bool:
        """Pede menos carga (batch, resolução ou frames). False = não suportado."""
        return False

    def restore_load(self) -> bool:
        return False

    def pause(self) -> bool:
        return False

    def resume(self) -> bool:
        return False

    def stop(self, reason: str) -> bool:
        return False


class CallbackJobControl(JobControl):
    """Para motores em processo: cada ação é uma função opcional."""

    def __init__(self, reduce: Optional[Callable[[], bool]] = None, restore: Optional[Callable[[], bool]] = None,
                 pause: Optional[Callable[[], bool]] = None, resume: Optional[Callable[[], bool]] = None,
                 stop: Optional[Callable[[str], bool]] = None):
        self._reduce, self._restore, self._pause, self._resume, self._stop = reduce, restore, pause, resume, stop

    def reduce_load(self) -> bool:
        return bool(self._reduce and self._reduce())

    def restore_load(self) -> bool:
        return bool(self._restore and self._restore())

    def pause(self) -> bool:
        return bool(self._pause and self._pause())

    def resume(self) -> bool:
        return bool(self._resume and self._resume())

    def stop(self, reason: str) -> bool:
        return bool(self._stop and self._stop(reason))


class ProcessJobControl(JobControl):
    """Controla um processo externo do próprio usuário (sem root).

    Pausa com SIGSTOP e retoma com SIGCONT no grupo de processos: o
    processo para de enviar trabalho à GPU, mas mantém a VRAM alocada.
    Encerramento: SIGTERM e, após ``grace`` segundos, SIGKILL.
    Um processo genérico não sabe reduzir carga: ``reduce_load`` = False.
    """

    def __init__(self, proc: subprocess.Popen, grace: float = 10.0):
        self.proc = proc
        self.grace = grace

    def _signal(self, sig: int) -> bool:
        if self.proc.poll() is not None:
            return False
        try:
            os.killpg(os.getpgid(self.proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            return False
        return True

    def pause(self) -> bool:
        return self._signal(signal.SIGSTOP)

    def resume(self) -> bool:
        return self._signal(signal.SIGCONT)

    def stop(self, reason: str) -> bool:
        self._signal(signal.SIGCONT)  # processo parado não trata SIGTERM
        if not self._signal(signal.SIGTERM):
            return False
        try:
            self.proc.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            self._signal(signal.SIGKILL)
            self.proc.wait()
        return True


class ActionDispatcher:
    """Traduz TRANSIÇÕES de nível em ações; repetir o mesmo nível não reage de novo."""

    def __init__(self, control: JobControl):
        self.control = control
        self.paused = False
        self.stopped = False

    def apply(self, decision: Decision) -> List[Dict]:
        events: List[Dict] = []
        if self.stopped:
            return events
        motivo = "; ".join(decision.reasons)
        lvl, prev = decision.level, decision.previous

        if lvl == CRITICO:
            ok = self.control.stop(motivo)
            self.stopped = True
            events.append({"acao": "encerrar", "ok": ok, "motivo": motivo})
            return events

        # Subida: reduz carga antes de pausar. Descida: retoma antes de restaurar.
        if lvl < PAUSAR and self.paused:
            ok = self.control.resume()
            self.paused = not ok
            events.append({"acao": "retomar", "ok": ok})

        if lvl >= REDUZIR > prev:
            ok = self.control.reduce_load()
            events.append({"acao": "reduzir_carga", "ok": ok,
                           "motivo": motivo if ok else "motor não suporta redução de carga"})
        elif lvl < REDUZIR <= prev:
            ok = self.control.restore_load()
            events.append({"acao": "restaurar_carga", "ok": ok})

        if lvl >= PAUSAR and not self.paused:
            ok = self.control.pause()
            self.paused = ok
            events.append({"acao": "pausar", "ok": ok, "motivo": motivo})
        return events
