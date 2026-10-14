"""Provedor para APIs textuais compatíveis (LM Studio, llama.cpp server)."""
from __future__ import annotations

import httpx

from app.core.models import ProviderError


class LocalCompatibleProvider:
    name = "local_compatible"

    def __init__(self, base_url: str, timeout: float = 120.0,
                 client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def generate(self, model: str, prompt: str, system: str | None = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        try:
            r = await self._client.post(
                "/v1/chat/completions", json={"model": model, "messages": messages, "stream": False})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"servidor respondeu {e.response.status_code}") from e
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"servidor local indisponível: {e}") from e

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get("/v1/models")
            r.raise_for_status()
            return sorted(m["id"] for m in r.json().get("data", []))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ProviderError(f"servidor local indisponível: {e}") from e
