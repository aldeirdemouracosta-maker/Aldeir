"""TestRunner: roda somente o pytest do workspace. NÃO é um sandbox.

Os testes executam código arbitrário do projeto com as permissões do usuário.
Nenhum comando vindo de um modelo de linguagem é executado por aqui.
"""
from __future__ import annotations

import sys

from app.terminal.processes import LimitedProcess, ProcResult
from app.terminal.workspace import Workspace


class TestRunner:
    __test__ = False  # evita coleta pelo pytest

    def __init__(self, ws: Workspace, timeout: float = 120.0) -> None:
        self.ws, self.timeout = ws, timeout

    def run(self, target: str | None = None) -> ProcResult:
        argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        if target:
            argv.append(self.ws.rel(self.ws.resolve(target)))
        return LimitedProcess(argv, self.ws.root, self.timeout).run()
