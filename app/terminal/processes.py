"""Execução limitada de processos: sem shell, timeout, saída truncada, mata o filho se interrompido."""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass
class ProcResult:
    returncode: int | None
    output: str
    timed_out: bool = False


def kill_tree(proc: subprocess.Popen) -> None:
    """Mata o processo e todos os descendentes (testes que abrem servidores, shells, etc.).
    `Popen.kill()` sozinho deixa os filhos órfãos tanto no Linux quanto no Windows."""
    try:
        parent = psutil.Process(proc.pid)
        victims = parent.children(recursive=True) + [parent]   # filhos primeiro, capturados antes de matar o pai
    except psutil.NoSuchProcess:
        return
    for p in victims:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


class LimitedProcess:
    def __init__(self, argv: list[str], cwd: Path, timeout: float, max_output: int = 20_000) -> None:
        self.argv, self.cwd, self.timeout, self.max_output = argv, cwd, timeout, max_output
        self._proc: subprocess.Popen | None = None

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
            kill_tree(self._proc)
            self._proc.wait()
        except BaseException:  # Ctrl+C: não deixa o filho (nem os netos) órfão
            kill_tree(self._proc)
            raise
        reader.join(timeout=5)
        out = "".join(chunks)
        if len(out) > self.max_output:
            out = out[: self.max_output] + "\n… (saída truncada)"
        return ProcResult(self._proc.returncode, out, timed_out)
