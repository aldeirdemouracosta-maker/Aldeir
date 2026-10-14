"""PatchManager: propõe, mostra diff, aplica com autorização, faz backup e desfaz."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.locking import FileLock
from app.core.models import SwarmError
from app.terminal.workspace import Workspace


class PatchError(SwarmError):
    pass


@dataclass
class Proposal:
    id: int
    path: str
    new_content: str
    base_sha: str | None  # None = arquivo novo
    diff: str


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PatchManager:
    def __init__(self, ws: Workspace, state_dir: Path | None = None) -> None:
        self.ws = ws
        self.dir = state_dir or ws.root / ".swarm"
        self._pending: dict[int, Proposal] = {}
        self._next = 1

    # --- proposta e diff (nunca escrevem no workspace) ---
    def propose(self, rel: str, new_content: str) -> Proposal:
        path = self.ws.resolve(rel, must_exist=False)
        if path.exists() and not path.is_file():
            raise PatchError(f"não é arquivo: {rel}")
        if self.dir.resolve() in path.parents:
            raise PatchError("não é permitido alterar o diretório de estado")
        old = self.ws.read(rel) if path.exists() else None
        if old == new_content:
            raise PatchError("proposta idêntica ao arquivo atual")
        diff = "".join(difflib.unified_diff(
            (old or "").splitlines(keepends=True), new_content.splitlines(keepends=True),
            fromfile=f"a/{rel}" if old is not None else "/dev/null", tofile=f"b/{rel}"))
        p = Proposal(self._next, rel, new_content, None if old is None else _sha(old), diff)
        self._pending[p.id] = p
        self._next += 1
        return p

    def get(self, pid: int) -> Proposal:
        try:
            return self._pending[pid]
        except KeyError:
            raise PatchError(f"proposta inexistente: {pid}") from None

    def pending(self) -> list[Proposal]:
        return list(self._pending.values())

    # --- aplicação autorizada ---
    def apply(self, pid: int, *, authorized: bool) -> Path:
        if authorized is not True:
            raise PatchError("aplicação requer autorização explícita")
        self.dir.mkdir(parents=True, exist_ok=True)
        with FileLock(self.dir / "patch.lock", owner="apply"):
            return self._apply_locked(pid)

    def _apply_locked(self, pid: int) -> Path:
        p = self.get(pid)
        path = self.ws.resolve(p.path, must_exist=False)
        current = self.ws.read(p.path) if path.exists() else None
        if (None if current is None else _sha(current)) != p.base_sha:
            raise PatchError("o arquivo mudou desde a proposta; gere outra")
        backup = None
        if current is not None:
            bdir = self.dir / "backups"
            bdir.mkdir(parents=True, exist_ok=True)
            backup = bdir / f"{int(time.time() * 1000)}-{p.id}.bak"
            backup.write_text(current, encoding="utf-8", newline="")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, p.new_content)
        self._log({"op": "apply", "id": p.id, "path": p.path,
                   "backup": backup.name if backup else None, "new_sha": _sha(p.new_content)})
        del self._pending[pid]
        return path

    def undo(self) -> str:
        """Desfaz a última aplicação ainda não desfeita."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with FileLock(self.dir / "patch.lock", owner="undo"):
            return self._undo_locked()

    def _undo_locked(self) -> str:
        stack: list[dict] = []
        for e in self._history():
            if e["op"] == "apply":
                stack.append(e)
            elif e["op"] == "undo" and stack:
                stack.pop()
        if not stack:
            raise PatchError("nada para desfazer")
        e = stack[-1]
        path = self.ws.resolve(e["path"], must_exist=False)
        if path.exists() and _sha(self.ws.read(e["path"])) != e["new_sha"]:
            raise PatchError("o arquivo foi alterado depois da aplicação; undo recusado")
        if e["backup"] is None:
            path.unlink(missing_ok=True)
        else:
            old = (self.dir / "backups" / e["backup"]).read_text(encoding="utf-8")
            self._atomic_write(path, old)
        self._log({"op": "undo", "id": e["id"], "path": e["path"]})
        return e["path"]

    def history(self) -> list[dict]:
        return self._history()

    # --- internos ---
    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".swarm-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _log(self, entry: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / "history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _history(self) -> list[dict]:
        f = self.dir / "history.jsonl"
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]
