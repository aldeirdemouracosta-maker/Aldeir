"""Busca simples (por palavras) na biblioteca – usada para dar exemplos reais ao LLM e como plano B."""

from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

from core.library import REGISTRY, CATEGORIES
from core.library.base import CircuitDef

SYNONYMS = {
    "pedal": "guitarra", "pedaleira": "guitarra", "distorcao": "overdrive fuzz guitarra", "efeito": "guitarra",
    "amplificador": "audio amp", "som": "audio", "caixa": "crossover audio", "alto-falante": "audio",
    "fonte": "fontes regulador", "regulador": "fontes ldo", "conversor": "buck boost fontes",
    "carro": "veiculos", "automotivo": "veiculos", "veicular": "veiculos", "bateria": "veiculos solar",
    "solar": "solar painel pv", "painel": "solar pv", "fotovoltaico": "solar pv",
    "radio": "radio_tv am", "tv": "radio_tv", "antena": "antenas", "rf": "antenas radio_tv",
    "placa": "computador", "cpu": "computador vrm", "computador": "computador", "memoria": "computador",
    "ia": "ia neuronio crossbar", "neural": "ia neuronio", "acelerador": "ia vrm gpu",
    "filtro": "filtro passa", "oscilador": "oscilador", "retificador": "retificador",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _tokens(s: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9_]+", _norm(s)) if len(t) > 1]


def search_library(query: str, k: int = 3) -> List[Tuple[float, CircuitDef]]:
    q = _tokens(query)
    expanded = list(q)
    for t in q:
        for key, extra in SYNONYMS.items():
            if t.startswith(_norm(key)[:5]):
                expanded += _tokens(extra)
    scored = []
    for c in REGISTRY.values():
        hay = _tokens(f"{c.id} {c.name} {c.summary} {CATEGORIES[c.category]} {c.category}")
        hs = set(hay)
        score = 0.0
        for t in expanded:
            if t in hs:
                score += 1.0
            elif any(h.startswith(t[:5]) for h in hs if len(t) >= 5):
                score += 0.5
        if score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]
