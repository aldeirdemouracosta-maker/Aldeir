"""Organização das pastas de saída e histórico de gerações.

Estrutura gerada::

    outputs/
      2026-10-03/
        framepack/
          143015_gato-pulando.mp4
          143015_gato-pulando.jpg      (miniatura)
          143015_gato-pulando.json     (metadados)
      history.json                     (índice de todas as gerações)
      _work/                           (arquivos temporários, apagados ao final)
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def slugify(text: str, max_len: int = 40) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug[:max_len].rstrip("-") or "video"


@dataclass
class HistoryEntry:
    id: str
    created_at: str
    mode: str
    prompt: str
    preset: str
    style: str
    duration_s: int
    profile: str
    seed: int
    video_path: str
    thumbnail_path: str | None = None
    elapsed_s: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        when = self.created_at.replace("T", " ")[:16]
        return f"{when} · {self.mode} · {self.duration_s}s"


class Storage:
    """Cria caminhos de saída e mantém ``history.json`` (thread-safe)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_file = root / "history.json"
        self._lock = threading.Lock()

    # ---------- caminhos ----------
    def new_output_base(self, mode: str, prompt: str) -> Path:
        """Caminho base (sem extensão) para o vídeo final de uma geração."""
        now = datetime.now()
        folder = self.root / now.strftime("%Y-%m-%d") / mode
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{now.strftime('%H%M%S')}_{slugify(prompt)}"

    def new_work_dir(self) -> Path:
        path = self.root / "_work" / uuid.uuid4().hex[:12]
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def cleanup(work_dir: Path) -> None:
        shutil.rmtree(work_dir, ignore_errors=True)

    # ---------- histórico ----------
    def load_history(self) -> list[HistoryEntry]:
        if not self.history_file.exists():
            return []
        try:
            raw = json.loads(self.history_file.read_text(encoding="utf-8"))
            entries = [HistoryEntry(**item) for item in raw]
        except (json.JSONDecodeError, TypeError) as exc:
            log.error("history.json corrompido (%s); um backup foi criado", exc)
            shutil.copyfile(self.history_file, self.history_file.with_suffix(".bak"))
            return []
        # Ignora entradas cujo vídeo foi apagado manualmente.
        return [e for e in entries if Path(e.video_path).exists()]

    def add_entry(self, entry: HistoryEntry) -> None:
        with self._lock:
            entries = self.load_history()
            entries.insert(0, entry)
            self._write(entries)
        Path(entry.video_path).with_suffix(".json").write_text(
            json.dumps(asdict(entry), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("Geração salva: %s", entry.video_path)

    def delete_entry(self, entry_id: str) -> None:
        with self._lock:
            entries = self.load_history()
            for e in entries:
                if e.id == entry_id:
                    for p in (e.video_path, e.thumbnail_path, str(Path(e.video_path).with_suffix(".json"))):
                        if p:
                            Path(p).unlink(missing_ok=True)
            self._write([e for e in entries if e.id != entry_id])

    def _write(self, entries: list[HistoryEntry]) -> None:
        tmp = self.history_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.history_file)


def new_entry_id() -> str:
    return uuid.uuid4().hex[:10]
