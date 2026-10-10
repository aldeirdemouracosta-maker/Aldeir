"""Exercise installed dependencies that unit doubles do not validate."""
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from support import WorkspaceTemp

from aether.agent.agent import show_plan
from aether.config import AetherConfig, VectorStoreConfig
from aether.indexer.vectorstore import VectorStore


class RuntimeDependencyTests(unittest.TestCase):
    def test_plan_preserves_literal_markup(self):
        output = StringIO()
        with redirect_stdout(output):
            show_plan("[bold]literal[/bold]")
        self.assertIn("[bold]literal[/bold]", output.getvalue())

    def test_config_defaults_are_validated_and_independent(self):
        first, second = AetherConfig(), AetherConfig()
        self.assertEqual(first.embedder.dimension, 768)
        first.indexer.include_extensions.append(".custom")
        self.assertNotIn(".custom", second.indexer.include_extensions)
        with self.assertRaises(ValueError):
            first.embedder.dimension = 0

    def test_real_lancedb_replace_search_reopen_and_empty(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        config = VectorStoreConfig(path=str(Path(temp.name) / "vectors"))
        store = VectorStore(config, dimension=2)
        self.assertEqual(store.count(), 0)
        row = {"id": "a:0", "path": "a.py", "chunk_index": 0,
               "content": "print(1)", "start_line": 1, "end_line": 1,
               "language": "python", "hash": "hash", "vector": [1.0, 2.0]}
        store.replace([row])
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.search([1.0, 2.0])[0]["id"], "a:0")
        reopened = VectorStore(config, dimension=2)
        self.assertEqual(reopened.get_records()[0]["content"], "print(1)")
        store.replace([])
        self.assertEqual(store.get_records(), [])
        self.assertEqual(store.count(), 0)
