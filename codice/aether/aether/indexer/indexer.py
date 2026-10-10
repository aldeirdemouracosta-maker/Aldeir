from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aether.indexer.cache import EmbeddingCache, valid_vector
from aether.indexer.embedder import Embedder

if TYPE_CHECKING:
    from aether.config import AetherConfig, IndexerConfig


@dataclass
class CodeChunk:
    path: str
    content: str
    chunk_index: int
    start_line: int
    end_line: int
    language: str
    hash: str


class CodebaseIndexer:
    """Indexes a codebase into a local vector store for semantic retrieval."""

    def __init__(self, config: AetherConfig, *, embedder: Any = None, store: Any = None):
        self.config = config
        self.indexer_cfg: IndexerConfig = config.indexer
        self.root = Path(config.project_root).resolve()
        if embedder is None:
            cache = None
            if config.cache.enabled:
                cache_path = (self.root / config.cache.path).resolve()
                if not cache_path.is_relative_to(self.root):
                    raise ValueError("Embedding cache outside project")
                cache = EmbeddingCache(cache_path, max_bytes=config.cache.max_bytes)
            embedder = Embedder(config.embedder, cache=cache)
        self.embedder = embedder
        if store is None:
            from aether.indexer.vectorstore import VectorStore
            store_config = config.vectorstore.model_copy()
            store_path = (self.root / store_config.path).resolve()
            if not store_path.is_relative_to(self.root):
                raise ValueError("Index outside project")
            store_config.path = str(store_path)
            store = VectorStore(store_config, dimension=config.embedder.dimension)
        self.store = store

    def index(self, force: bool = False) -> dict[str, Any]:
        """Stage a complete update before replacing any previous index rows."""
        files = list(self._discover_files())
        existing: dict[str, list[dict[str, Any]]] = {}
        for record in self.store.get_records():
            existing.setdefault(record["path"], []).append(record)
        paths = {str(path.relative_to(self.root)) for path in files}
        stats = {"files": 0, "chunks": 0, "skipped": 0,
                 "deleted": len(set(existing) - paths)}
        staged = []
        for path in files:
            relative = str(path.relative_to(self.root))
            # Reading failures abort instead of silently deleting previous rows.
            chunks = list(self._chunk_file(path, relative))
            old = sorted(existing.get(relative, []), key=lambda r: r["chunk_index"])
            signature = [(chunk.hash, chunk.start_line, chunk.end_line) for chunk in chunks]
            old_signature = [(r["hash"], r["start_line"], r["end_line"]) for r in old]
            vectors_valid = True
            try:
                for record in old:
                    valid_vector(record["vector"], self.config.embedder.dimension)
            except (ValueError, TypeError):
                vectors_valid = False
            if not force and signature == old_signature and vectors_valid:
                staged.extend(old)
                stats["skipped"] += 1
                continue
            vectors = self.embedder.embed([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError("Embedding count mismatch; previous index preserved")
            for chunk, vector in zip(chunks, vectors, strict=True):
                staged.append({"id": f"{chunk.path}:{chunk.chunk_index}",
                    "path": chunk.path, "chunk_index": chunk.chunk_index,
                    "content": chunk.content, "start_line": chunk.start_line,
                    "end_line": chunk.end_line, "language": chunk.language,
                    "hash": chunk.hash,
                    "vector": valid_vector(vector, self.config.embedder.dimension)})
            stats["files"] += 1
            stats["chunks"] += len(chunks)
        # Also handles an entirely emptied project; --force never clears upfront.
        if force or stats["files"] or stats["deleted"]:
            self.store.replace(staged)
        return stats

    def close(self) -> None:
        close = getattr(self.embedder, "close", None)
        if close:
            close()

    def search(self, query: str, limit: int = 12) -> list[dict[str, Any]]:
        """Semantic search over the indexed codebase."""
        if not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Search requires nonempty query and limit 1..100")
        vector = self.embedder.embed_query(query)
        results = self.store.search(vector, limit=limit)
        return results

    def _discover_files(self) -> Iterator[Path]:
        def discovery_error(error: OSError) -> None:
            raise error
        for root, dirs, files in os.walk(self.root, onerror=discovery_error):
            # Filtra diretórios excluídos in-place
            dirs[:] = [
                d for d in dirs
                if d not in self.indexer_cfg.exclude_dirs and not d.startswith(".")
                and not (Path(root) / d).is_symlink()
                and not (Path(root) / d).is_junction()
            ]

            for name in files:
                path = Path(root) / name
                if self._should_index(path):
                    yield path

    def _should_index(self, path: Path) -> bool:
        if not path.resolve().is_relative_to(self.root):
            return False
        if path.suffix.lower() not in self.indexer_cfg.include_extensions:
            return False

        try:
            size_kb = path.stat().st_size / 1024
            if size_kb > self.indexer_cfg.max_file_size_kb:
                return False
        except OSError:
            return False

        return True

    def _chunk_file(self, path: Path, rel_path: str) -> Iterator[CodeChunk]:
        text = path.read_text(encoding="utf-8", errors="strict")

        if not text.strip():
            return

        language = self._detect_language(path)
        lines = text.splitlines(keepends=True)

        chunk_size = self.indexer_cfg.chunk_size
        overlap = self.indexer_cfg.chunk_overlap

        current_chunk: list[str] = []
        current_len = 0
        start_line = 1
        chunk_index = 0

        for i, line in enumerate(lines, start=1):
            line_len = len(line)

            if current_len + line_len > chunk_size and current_chunk:
                content = "".join(current_chunk)
                yield CodeChunk(
                    path=rel_path,
                    content=content,
                    chunk_index=chunk_index,
                    start_line=start_line,
                    end_line=i - 1,
                    language=language,
                    hash=Embedder.hash_text(content),
                )
                chunk_index += 1

                # Overlap: mantém as últimas linhas
                overlap_lines: list[str] = []
                overlap_len = 0
                for overlap_line in reversed(current_chunk):
                    if overlap_len + len(overlap_line) > overlap:
                        break
                    overlap_lines.insert(0, overlap_line)
                    overlap_len += len(overlap_line)

                current_chunk = overlap_lines
                current_len = overlap_len
                start_line = i - len(overlap_lines)

            current_chunk.append(line)
            current_len += line_len

        # Último chunk
        if current_chunk:
            content = "".join(current_chunk)
            yield CodeChunk(
                path=rel_path,
                content=content,
                chunk_index=chunk_index,
                start_line=start_line,
                end_line=len(lines),
                language=language,
                hash=Embedder.hash_text(content),
            )

    def _detect_language(self, path: Path) -> str:
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "jsx",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".html": "html",
            ".css": "css",
        }
        return ext_map.get(path.suffix.lower(), "text")
