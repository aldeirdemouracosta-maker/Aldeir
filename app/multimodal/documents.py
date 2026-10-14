"""Chunking e DocumentIndex (SQLite) para RAG. Busca por similaridade de cosseno em Python puro."""
from __future__ import annotations

import array
import hashlib
import math
import sqlite3
import threading
from pathlib import Path
from typing import Awaitable, Callable

Embed = Callable[[str], Awaitable[list[float]]]


def chunk_text(text: str, max_chars: int = 800) -> list[tuple[int, int, str]]:
    """Divide por linhas. Retorna (linha_inicial, linha_final, trecho), linhas 1-based."""
    chunks, buf, start, size = [], [], 1, 0
    for n, line in enumerate(text.splitlines(), 1):
        if buf and size + len(line) > max_chars:
            chunks.append((start, n - 1, "\n".join(buf)))
            buf, start, size = [], n, 0
        buf.append(line)
        size += len(line) + 1
    if any(l.strip() for l in buf):
        chunks.append((start, start + len(buf) - 1, "\n".join(buf)))
    return [c for c in chunks if c[2].strip()]


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


class DocumentIndex:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
              create table if not exists docs(path text primary key, sha text not null, model text not null);
              create table if not exists chunks(id integer primary key autoincrement, path text not null,
                  line_start int, line_end int, text text not null, dim int not null, emb blob not null);
              create index if not exists chunks_path on chunks(path);
              create table if not exists images(path text primary key, sha text not null,
                  dim int not null, emb blob not null);
            """)

    async def index_text(self, path: str, text: str, embed: Embed, model: str) -> int:
        """Indexa (ou reindexa se mudou). Retorna nº de trechos; 0 se já estava atualizado."""
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            row = self._db.execute("select sha, model from docs where path=?", (path,)).fetchone()
        if row == (sha, model):
            return 0
        rows = []
        for a, b, t in chunk_text(text):
            emb = array.array("f", await embed(t))  # falha aqui não altera o índice anterior
            rows.append((path, a, b, t, len(emb), emb.tobytes()))
        with self._lock, self._db:
            self._db.execute("delete from chunks where path=?", (path,))
            self._db.executemany(
                "insert into chunks(path,line_start,line_end,text,dim,emb) values(?,?,?,?,?,?)", rows)
            self._db.execute("insert or replace into docs values(?,?,?)", (path, sha, model))
        return len(rows)

    def search(self, query_emb: list[float], k: int = 5) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "select path,line_start,line_end,text,emb from chunks where dim=?",
                (len(query_emb),)).fetchall()
        scored = []
        for path, a, b, text, blob in rows:
            emb = array.array("f")
            emb.frombytes(blob)
            scored.append({"path": path, "line_start": a, "line_end": b,
                           "score": round(cosine(query_emb, list(emb)), 4), "text": text})
        return sorted(scored, key=lambda r: -r["score"])[: max(1, min(k, 20))]

    def index_image(self, path: str, sha: str, emb: list[float]) -> bool:
        """Retorna False se a imagem já estava indexada com o mesmo conteúdo."""
        with self._lock:
            row = self._db.execute("select sha from images where path=?", (path,)).fetchone()
        if row and row[0] == sha:
            return False
        blob = array.array("f", emb).tobytes()
        with self._lock, self._db:
            self._db.execute("insert or replace into images values(?,?,?,?)", (path, sha, len(emb), blob))
        return True

    def search_images(self, query_emb: list[float], k: int = 5) -> list[dict]:
        with self._lock:
            rows = self._db.execute("select path, emb from images where dim=?", (len(query_emb),)).fetchall()
        scored = []
        for path, blob in rows:
            emb = array.array("f")
            emb.frombytes(blob)
            scored.append({"path": path, "score": round(cosine(query_emb, list(emb)), 4)})
        return sorted(scored, key=lambda r: -r["score"])[: max(1, min(k, 20))]

    def stats(self) -> dict:
        with self._lock:
            d = self._db.execute("select count(*) from docs").fetchone()[0]
            c = self._db.execute("select count(*) from chunks").fetchone()[0]
            i = self._db.execute("select count(*) from images").fetchone()[0]
        return {"documents": d, "chunks": c, "images": i}

    def close(self) -> None:
        with self._lock:
            self._db.close()
