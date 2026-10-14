"""Interface mínima de provedor de modelos de texto."""
from __future__ import annotations

from typing import Protocol


class Provider(Protocol):
    name: str

    async def generate(self, model: str, prompt: str, system: str | None = None) -> str: ...

    async def list_models(self) -> list[str]: ...
