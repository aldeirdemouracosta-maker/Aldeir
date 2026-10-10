import copy
import unittest
from pathlib import Path
from types import SimpleNamespace

from support import WorkspaceTemp

from aether.indexer.indexer import CodebaseIndexer


class MemoryStore:
    def __init__(self):
        self.records = []
        self.replacements = 0
    def get_records(self):
        return copy.deepcopy(self.records)
    def replace(self, records):
        self.records = copy.deepcopy(records)
        self.replacements += 1


class StubEmbedder:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.bad_count = False
        self.bad_vector = False
    def embed(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Embedding unavailable")
        if self.bad_count:
            return []
        return [[0, 0] if self.bad_vector else [1, 2] for _ in texts]


class IndexerTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = SimpleNamespace(project_root=self.root, embedder=SimpleNamespace(dimension=2),
            indexer=SimpleNamespace(chunk_size=100, chunk_overlap=10, include_extensions=[".py"],
                                    exclude_dirs=[], max_file_size_kb=500))
        self.embedder = StubEmbedder()
        self.store = MemoryStore()
        self.indexer = CodebaseIndexer(config, embedder=self.embedder, store=self.store)
        self.file = self.root / "a.py"
        self.file.write_text("print('initial')", encoding="utf-8")

    def test_hash_incremental_changed_files(self):
        self.indexer.index()
        self.assertEqual(self.indexer.index()["skipped"], 1)
        self.assertEqual(self.embedder.calls, 1)
        self.file.write_text("print('changed')", encoding="utf-8")
        self.assertEqual(self.indexer.index()["files"], 1)
        self.assertEqual(self.embedder.calls, 2)
        self.assertIn("changed", self.store.records[0]["content"])

    def test_deleted_files_and_empty_project(self):
        self.indexer.index()
        self.file.unlink()
        self.assertEqual(self.indexer.index()["deleted"], 1)
        self.assertEqual(self.store.records, [])

    def test_emptied_file_removes_chunks(self):
        self.indexer.index()
        self.file.write_text("")
        self.indexer.index()
        self.assertEqual(self.store.records, [])

    def test_embedding_failure_preserves_entire_previous_index(self):
        self.indexer.index()
        old = copy.deepcopy(self.store.records)
        self.file.write_text("changed")
        self.embedder.fail = True
        for force in [False, True]:
            with self.assertRaises(RuntimeError):
                self.indexer.index(force=force)
            self.assertEqual(self.store.records, old)
            self.assertEqual(self.store.replacements, 1)

    def test_partial_update_not_committed_on_later_failure(self):
        self.indexer.index()
        old = copy.deepcopy(self.store.records)
        (self.root / "b.py").write_text("new file")
        self.embedder.fail = True
        with self.assertRaises(RuntimeError):
            self.indexer.index()
        self.assertEqual(self.store.records, old)

    def test_invalid_embeddings_preserve_index(self):
        self.indexer.index()
        old = copy.deepcopy(self.store.records)
        self.file.write_text("changed")
        for attr in ["bad_count", "bad_vector"]:
            setattr(self.embedder, attr, True)
            with self.assertRaises(ValueError):
                self.indexer.index()
            self.assertEqual(self.store.records, old)
            setattr(self.embedder, attr, False)

    def test_read_failure_preserves_index(self):
        self.indexer.index()
        old = copy.deepcopy(self.store.records)
        self.file.write_bytes(b"\xff\xfe")
        with self.assertRaises(UnicodeError):
            self.indexer.index()
        self.assertEqual(self.store.records, old)

    def test_outside_project_not_indexed(self):
        self.assertFalse(self.indexer._should_index(self.root.parent / "outside.py"))
