"""Provedor Ollama (API nativa). Nunca baixa modelos sozinho."""
from __future__ import annotations

import httpx

from app.core.models import ProviderError
from app.providers.base import strip_think


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, timeout: float = 120.0,
                 client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(self, model: str, prompt: str, system: str | None = None) -> str:
        body: dict = {"model": model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        try:
            r = await self._client.post("/api/generate", json=body)
            r.raise_for_status()
            return strip_think(r.json()["response"])
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Ollama respondeu {e.response.status_code}: {e.response.text[:200]}") from e
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ProviderError(f"Ollama indisponível: {e}") from e

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get("/api/tags")
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ProviderError(f"Ollama indisponível: {e}") from e

    async def loaded_models(self) -> list[str]:
        try:
            r = await self._client.get("/api/ps")
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ProviderError(f"Ollama indisponível: {e}") from e

    async def embed(self, model: str, text: str) -> list[float]:
        try:
            r = await self._client.post("/api/embed", json={"model": model, "input": text})
            r.raise_for_status()
            return [float(x) for x in r.json()["embeddings"][0]]
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Ollama respondeu {e.response.status_code} ao gerar embedding") from e
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:
            raise ProviderError(f"Ollama indisponível: {e}") from e
