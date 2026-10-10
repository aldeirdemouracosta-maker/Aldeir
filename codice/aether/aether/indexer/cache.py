"""SQLite cache for embeddings only; no text, commands or test results stored."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

PROCESSING_VERSION = "aether-embedding-v1"


def valid_vector(value: Any, dimension: int) -> list[float]:
    try:
        valid = (isinstance(value, list) and len(value) == dimension and any(value)
                 and all(type(number) in (int, float) and math.isfinite(number)
                         and abs(number) <= 3.4028235e38 for number in value))
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError("Embedding must be finite, nonzero and match configured dimension")
    return [float(number) for number in value]


def cache_key(text: str, *, model: str, digest: str | None, endpoint: str,
              dimension: int, parameters: dict[str, Any] | None = None,
              processing_version: str = PROCESSING_VERSION) -> str | None:
    # Without a verifiable digest, persistently reusing a model tag is unsafe.
    if not digest:
        return None
    identity = {"text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "model": model, "digest": digest, "endpoint": endpoint,
                "dimension": dimension, "parameters": parameters or {},
                "processing_version": processing_version}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()


class EmbeddingCache:
    def __init__(self, path: Path, *, max_bytes: int = 128 * 1024 * 1024):
        if max_bytes < 65536:
            raise ValueError("Embedding cache requires at least 64 KiB")
        self.path = path
        self.max_bytes = max_bytes
        self.hits = self.misses = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA auto_vacuum=FULL")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("CREATE TABLE IF NOT EXISTS embeddings "
                        "(key TEXT PRIMARY KEY, vector TEXT NOT NULL, used REAL NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS metrics "
                        "(name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
        self.db.executemany("INSERT OR IGNORE INTO metrics VALUES (?, 0)",
                            [("hits",), ("misses",)])
        self.db.commit()
        self._trim()

    def get(self, key: str | None, dimension: int) -> list[float] | None:
        row = self.db.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
        if row is not None:
            try:
                vector = valid_vector(json.loads(row[0]), dimension)
            except (ValueError, TypeError, OverflowError):
                with self.db:
                    self.db.execute("DELETE FROM embeddings WHERE key=?", (key,))
            else:
                self.hits += 1
                with self.db:
                    self.db.execute("UPDATE metrics SET value=value+1 WHERE name='hits'")
                    self.db.execute("UPDATE embeddings SET used=? WHERE key=?", (time.time(), key))
                return vector
        self.misses += 1
        with self.db:
            self.db.execute("UPDATE metrics SET value=value+1 WHERE name='misses'")
        return None

    def put(self, key: str | None, vector: list[float], dimension: int) -> None:
        vector = valid_vector(vector, dimension)
        if key is None:
            return
        payload = json.dumps(vector, allow_nan=False)
        # Avoid creating an oversized transient database for an uncacheable row.
        if len(key.encode()) + len(payload.encode()) + 24576 > self.max_bytes:
            return
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)",
                            (key, payload, time.time()))
        self._trim()

    def _trim(self) -> None:
        if self.storage_bytes <= self.max_bytes:
            return
        while self.storage_bytes > self.max_bytes:
            row = self.db.execute("SELECT key FROM embeddings ORDER BY used, key LIMIT 1").fetchone()
            if row is None:
                break
            with self.db:
                self.db.execute("DELETE FROM embeddings WHERE key=?", row)
        # Also compacts a cache opened with a smaller configured budget.
        self.db.execute("VACUUM")

    @property
    def storage_bytes(self) -> int:
        pages = self.db.execute("PRAGMA page_count").fetchone()[0]
        page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        return int(pages * page_size)

    def metrics(self) -> dict[str, int]:
        totals = dict(self.db.execute("SELECT name, value FROM metrics"))
        return {"hits": totals["hits"], "misses": totals["misses"],
                "session_hits": self.hits, "session_misses": self.misses,
                "storage_bytes": self.storage_bytes,
                "entries": self.db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]}

    def invalidate(self) -> int:
        count = self.db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        with self.db:
            self.db.execute("DELETE FROM embeddings")
        self.db.execute("VACUUM")
        return int(count)

    def close(self) -> None:
        self.db.close()
