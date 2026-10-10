import unittest
from pathlib import Path
from types import SimpleNamespace

from support import WorkspaceTemp

from aether.indexer.cache import EmbeddingCache, cache_key, valid_vector
from aether.indexer.embedder import Embedder


class FakeResponse:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class FakeClient:
    def __init__(self):
        self.digest = "digest-one"
        self.embedding_calls = 0
        self.remote = False
        self.vector = [1.0, 2.0]
    def post(self, url, json):
        if url.endswith("/api/show"):
            return FakeResponse({"remote_host": "cloud"} if self.remote else {})
        assert url == "http://localhost:11434/api/embeddings"
        self.embedding_calls += 1
        return FakeResponse({"embedding": self.vector})
    def get(self, url):
        assert url == "http://localhost:11434/api/tags"
        return FakeResponse({"models": [{"name": "test:latest", "digest": self.digest}]})
    def close(self):
        pass


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "cache.sqlite3"
        self.cache = EmbeddingCache(self.path, max_bytes=65536)
        self.addCleanup(lambda: self.cache.close())
        self.config = SimpleNamespace(base_url="http://localhost:11434", model="test",
            provider="ollama", dimension=2, parameters={})
        self.client = FakeClient()
        self.embedder = Embedder(self.config, client=self.client, cache=self.cache)

    def key(self, text="text", **options):
        identity = {"model": "test", "digest": "one", "endpoint": "http://localhost:11434",
                    "dimension": 2}
        identity.update(options)
        return cache_key(text, **identity)

    def test_reuse_and_metrics(self):
        self.embedder.embed(["exact text", "exact text"])
        self.assertEqual(self.client.embedding_calls, 1)
        self.assertEqual(self.cache.metrics()["hits"], 1)
        self.assertEqual(self.cache.metrics()["misses"], 1)

    def test_persistent_reuse(self):
        key = self.key()
        self.cache.put(key, [1, 2], 2)
        other = EmbeddingCache(self.path, max_bytes=65536)
        try:
            self.assertEqual(other.get(key, 2), [1, 2])
        finally:
            other.close()

    def test_explicit_invalidation(self):
        self.embedder.embed(["text"])
        self.assertEqual(self.cache.invalidate(), 1)
        self.embedder.embed(["text"])
        self.assertEqual(self.client.embedding_calls, 2)

    def test_identity_changes(self):
        key = self.key()
        for options in [{"digest": "two"}, {"model": "other"}, {"dimension": 3},
                        {"parameters": {"truncate": False}}, {"processing_version": "v2"}]:
            self.assertNotEqual(key, self.key(**options))
        self.assertNotEqual(key, self.key("text "))
        self.embedder.embed(["text"])
        self.client.digest = "digest-two"
        self.embedder.embed(["text"])
        self.assertEqual(self.client.embedding_calls, 2)

    def test_missing_digest_disables_persistence(self):
        self.client.digest = None
        self.embedder.embed(["text", "text"])
        self.assertEqual(self.client.embedding_calls, 2)
        self.assertEqual(self.cache.metrics()["entries"], 0)
        self.assertEqual(self.cache.metrics()["misses"], 2)

    def test_digest_endpoint_unavailable_uses_local_embedding_without_cache(self):
        def unavailable(url):
            raise RuntimeError("Tags unavailable")
        self.client.get = unavailable
        self.assertEqual(self.embedder.embed(["text"]), [[1, 2]])
        self.assertEqual(self.cache.metrics()["entries"], 0)

    def test_invalid_vectors_rejected(self):
        for value in [[], [0, 0], [True, 1], [float("nan"), 1], [float("inf"), 1],
                      [1e300, 1], ["1", 2], [1, 2, 3]]:
            with self.assertRaises(ValueError):
                valid_vector(value, 2)
        self.client.vector = [0, 0]
        with self.assertRaises(ValueError):
            self.embedder.embed(["text"])
        self.assertEqual(self.cache.metrics()["entries"], 0)

    def test_corrupt_cache_entry_not_reused(self):
        key = self.key()
        self.cache.db.execute("INSERT INTO embeddings VALUES (?, ?, 0)", (key, "[0, 0]"))
        self.cache.db.commit()
        self.assertIsNone(self.cache.get(key, 2))
        self.assertEqual(self.cache.metrics()["entries"], 0)

    def test_storage_budget(self):
        for index in range(100):
            self.cache.put(str(index), [float(index + 1)] * 1000, 1000)
        self.assertLessEqual(self.cache.storage_bytes, 65536)
        self.assertLess(self.cache.metrics()["entries"], 100)

    def test_remote_model_rejected_even_with_cache(self):
        self.embedder.embed(["text"])
        self.client.remote = True
        with self.assertRaises(ValueError):
            self.embedder.embed(["text"])
        self.assertEqual(self.client.embedding_calls, 1)
