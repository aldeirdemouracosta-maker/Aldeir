from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from aether.indexer.cache import EmbeddingCache, cache_key, valid_vector
from aether.llm.local import ensure_local_model, model_digest
from aether.security import local_url

if TYPE_CHECKING:
    from aether.config import EmbedderConfig


class Embedder:
    """Local embedder using preinstalled Ollama models."""

    def __init__(self, config: EmbedderConfig, *, client: Any = None,
                 cache: EmbeddingCache | None = None):
        self.config = config
        self.base_url = local_url(config.base_url)
        if client is None:
            import httpx
            client = httpx.Client(timeout=60.0, trust_env=False, follow_redirects=False)
        self._client = client
        self.cache = cache
        self.digest: str | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.config.provider == "ollama":
            return self._embed_ollama(texts)
        else:
            raise NotImplementedError(
                f"Provider '{self.config.provider}' not implemented yet. Use 'ollama'."
            )

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        ensure_local_model(self._client, self.base_url, self.config.model)
        try:
            self.digest = model_digest(self._client, self.base_url, self.config.model)
        except Exception:
            logging.getLogger(__name__).exception("Model digest unavailable; persistence disabled")
            # Metadata unavailability disables persistent cache, not local inference.
            self.digest = None
        embeddings = []
        url = f"{self.base_url}/api/embeddings"

        for text in texts:
            parameters = getattr(self.config, "parameters", {})
            key = cache_key(text, model=self.config.model, digest=self.digest,
                            endpoint=self.base_url, dimension=self.config.dimension,
                            parameters=parameters)
            cached = self.cache.get(key, self.config.dimension) if self.cache else None
            if cached is not None:
                embeddings.append(cached)
                continue
            payload = {
                "model": self.config.model,
                "prompt": text,
                "options": parameters,
            }
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            vector = valid_vector(data["embedding"], self.config.dimension)
            if self.cache:
                self.cache.put(key, vector, self.config.dimension)
            embeddings.append(vector)
        return embeddings

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def close(self) -> None:
        self._client.close()
        if self.cache:
            self.cache.close()
