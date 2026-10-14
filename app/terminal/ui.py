"""Coding Terminal: /edit → /diff → /apply → /test → /undo (fluxo supervisionado)."""
from __future__ import annotations

import re
from collections.abc import Callable

from app.core.models import SwarmError
from app.terminal.memory import SessionMemory
from app.terminal.patches import PatchError, PatchManager
from app.terminal.runner import TestRunner
from app.terminal.workspace import Workspace

HELP = """/ls  /read <arq>  /search <regex>  /edit <arq> <instrução>
/diff [id]  /apply [id]  /test [arq]  /undo  /history  /help  /quit"""

EDIT_SYSTEM = ("Você edita um arquivo. Responda SOMENTE com o conteúdo completo e novo do arquivo, "
               "sem explicações.")
_FENCE = re.compile(r"^```[\w+-]*\n(.*?)\n```\s*$", re.DOTALL)


def strip_fence(text: str) -> str:
    m = _FENCE.match(text.strip())
    return (m.group(1) if m else text).rstrip("\n") + "\n"


class Terminal:
    def __init__(self, ws: Workspace, provider, model: str, memory: SessionMemory | None = None,
                 confirm: Callable[[str], bool] = lambda _: False, runner: TestRunner | None = None) -> None:
        self.ws, self.provider, self.model = ws, provider, model
        self.memory = memory or SessionMemory()
        self.patches = PatchManager(ws)
        self.runner = runner or TestRunner(ws)
        self.confirm = confirm  # padrão: nega. Aplicação exige "sim" explícito do usuário.

    async def handle(self, line: str) -> str:
        cmd, _, arg = line.strip().partition(" ")
        try:
            return await self._dispatch(cmd, arg.strip())
        except SwarmError as e:
            return f"erro: {e}"

    async def _dispatch(self, cmd: str, arg: str) -> str:
        if cmd == "/help":
            return HELP
        if cmd == "/ls":
            return self.ws.tree()
        if cmd == "/read":
            text = self.ws.read(arg)
            self.memory.touch_file(arg)
            return text
        if cmd == "/search":
            hits = self.ws.search(arg)
            return "\n".join(f"{p}:{n}: {t}" for p, n, t in hits) or "nenhum resultado"
        if cmd == "/edit":
            return await self._edit(arg)
        if cmd == "/diff":
            return self._pick(arg).diff
        if cmd == "/apply":
            return self._apply(arg)
        if cmd == "/test":
            r = self.runner.run(arg or None)
            status = "TIMEOUT" if r.timed_out else f"código {r.returncode}"
            return f"[{status}]\n{r.output}"
        if cmd == "/undo":
            return f"desfeito: {self.patches.undo()}"
        if cmd == "/history":
            return "\n".join(f"{e['op']} #{e['id']} {e['path']}" for e in self.patches.history()) or "vazio"
        return f"comando desconhecido: {cmd!r} (/help)"

    async def _edit(self, arg: str) -> str:
        path, _, instruction = arg.partition(" ")
        if not path or not instruction.strip():
            return "uso: /edit <arquivo> <instrução>"
        exists = self.ws.resolve(path, must_exist=False).exists()
        current = self.ws.read(path) if exists else ""
        self.memory.touch_file(path)
        self.memory.add_turn("user", f"/edit {arg}")
        prompt = f"Contexto:\n{self.memory.context()}\n\nArquivo {path}:\n{current}\n\nInstrução: {instruction}"
        reply = await self.provider.generate(self.model, prompt, system=EDIT_SYSTEM)
        p = self.patches.propose(path, strip_fence(reply))
        self.memory.add_turn("assistant", f"proposta #{p.id} para {path}")
        return f"proposta #{p.id} criada (nada foi alterado). Veja /diff {p.id} e confirme com /apply {p.id}."

    def _pick(self, arg: str):
        if arg:
            if not arg.isdigit():
                raise PatchError(f"id inválido: {arg!r}")
            return self.patches.get(int(arg))
        pend = self.patches.pending()
        if not pend:
            raise PatchError("nenhuma proposta pendente")
        return pend[-1]

    def _apply(self, arg: str) -> str:
        p = self._pick(arg)
        if not self.confirm(f"Aplicar proposta #{p.id} em {p.path}?"):
            return "não aplicado (sem autorização)."
        path = self.patches.apply(p.id, authorized=True)
        return f"aplicado em {self.ws.rel(path)}. Backup guardado; use /undo para reverter."
