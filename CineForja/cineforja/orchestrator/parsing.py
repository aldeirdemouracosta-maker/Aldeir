"""Interpretação tolerante da saída do LLM."""
from __future__ import annotations

import json
import re


def parse_shots(text: str, n: int) -> list[str] | None:
    """Extrai uma lista de prompts de shots de {"shots": [...]} ou de uma lista JSON.

    Retorna None se a saída não for utilizável (o chamador usa o storyboard padrão).
    """
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except ValueError:
        return None
    items = data.get("shots") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    out = []
    for it in items:
        if isinstance(it, dict):
            it = it.get("prompt") or it.get("description")
        if isinstance(it, str) and it.strip():
            out.append(it.strip())
    return out[:n] if out else None
