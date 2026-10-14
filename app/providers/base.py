"""Interface mínima de provedor de modelos de texto."""
from __future__ import annotations

import re
from typing import Protocol

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove o raciocínio interno (<think>…</think>) de modelos como o Qwen3.

    Raciocínio sem fechamento (resposta cortada no meio) vira texto vazio: melhor falhar do que
    entregar raciocínio parcial como se fosse a resposta."""
    text = _THINK.sub("", text)
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


class Provider(Protocol):
    name: str

    async def generate(self, model: str, prompt: str, system: str | None = None) -> str: ...

    async def list_models(self) -> list[str]: ...
