"""Execução limitada de processos: sem shell, timeout, saída truncada, cancelável."""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcResult:
    returncode: int | None
    output: str
    timed_out: bool = False
    cancelled: bool = False


class LimitedProcess:
    def __init__(self, argv: list[str], cwd: Path, timeout: float, max_output: int = 20_000) -> None:
        self.argv, self.cwd, self.timeout, self.max_output = argv, cwd, timeout, max_output
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def run(self) -> ProcResult:
        self._proc = subprocess.Popen(
            self.argv, cwd=self.cwd, shell=False, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        chunks: list[str] = []
        reader = threading.Thread(target=lambda: chunks.append(self._proc.stdout.read()), daemon=True)
        reader.start()
        timed_out = False
        try:
            self._proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._proc.kill()
            self._proc.wait()
        reader.join(timeout=5)
        out = "".join(chunks)
        if len(out) > self.max_output:
            out = out[: self.max_output] + "\n… (saída truncada)"
        return ProcResult(self._proc.returncode, out, timed_out, self._cancelled)
