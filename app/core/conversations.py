"""ConversationStore: memória de conversa por sessão (SQLite). Separada do estado dos agentes e da auditoria.

Guarda TEXTO das conversas, localmente, por escolha explícita do usuário (campo `session`). Sem `session`
nada é gravado. Limites: mensagens e tamanho por sessão são podados para a memória não crescer sem fim.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

from app.core.models import SwarmError

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_STORED = 40          # mensagens guardadas por sessão
MAX_MESSAGE_CHARS = 8_000


class ConversationError(SwarmError):
    pass


def check_session(session: object) -> str:
    if not isinstance(session, str) or not SESSION_RE.match(session):
        raise ConversationError("session deve ter 1-64 caracteres: letras, números, '-' ou '_'")
    return session


class ConversationStore:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute("create table if not exists messages(id integer primary key autoincrement, "
                             "session text not null, ts real not null, role text not null, content text not null)")
            self._db.execute("create index if not exists messages_session on messages(session, id)")

    def add(self, session: str, role: str, content: str) -> None:
        if role not in ("user", "assistant"):
            raise ConversationError(f"papel inválido: {role!r}")
        with self._lock, self._db:
            self._db.execute("insert into messages(session, ts, role, content) values(?,?,?,?)",
                             (check_session(session), time.time(), role, content[:MAX_MESSAGE_CHARS]))
            self._db.execute("delete from messages where session=? and id not in "
                             "(select id from messages where session=? order by id desc limit ?)",
                             (session, session, MAX_STORED))

    def history(self, session: str, max_messages: int = 12, max_chars: int = 6_000) -> list[dict]:
        """Mensagens mais recentes que cabem nos limites, em ordem cronológica."""
        with self._lock:
            rows = self._db.execute("select role, content from messages where session=? order by id desc limit ?",
                                    (check_session(session), max_messages)).fetchall()
        out, used = [], 0
        for role, content in rows:                      # da mais nova para a mais antiga
            if used + len(content) > max_chars and out:
                break
            out.append({"role": role, "content": content})
            used += len(content)
        return out[::-1]

    def clear(self, session: str) -> int:
        with self._lock, self._db:
            return self._db.execute("delete from messages where session=?", (check_session(session),)).rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()
