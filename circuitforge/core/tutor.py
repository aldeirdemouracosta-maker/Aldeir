"""Instrutor offline (sem IA): lição em Markdown e quiz determinístico a partir das fórmulas do circuito."""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from .library.base import CircuitDef


def fmt(value: float, unit: str = "") -> str:
    """Formata com prefixo SI: 0.0001 → '100 µ'."""
    if value == 0:
        return f"0 {unit}".strip()
    prefixes = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")]
    a = abs(value)
    for scale, p in prefixes:
        if a >= scale:
            return f"{value / scale:.4g} {p}{unit}".strip()
    return f"{value:.3g} {unit}".strip()


def lesson_markdown(cdef: CircuitDef, params: Optional[Dict[str, float]] = None) -> str:
    L = cdef.lesson
    parts = [f"### {cdef.name}", f"_{cdef.summary}_"]
    if L.objetivo:
        parts += ["**🎯 Objetivo**", L.objetivo]
    if L.teoria:
        parts += ["**📘 Teoria**"] + [f"- {t}" for t in L.teoria]
    th = cdef.theory_values(params)
    if th:
        parts += ["**🧮 Valores teóricos (com seus parâmetros)**"] + [f"- {k}: **{fmt(v[0], v[1])}**" for k, v in th.items()]
    if L.observe:
        parts += ["**👀 O que observar**"] + [f"- {t}" for t in L.observe]
    if L.experimentos:
        parts += ["**🧪 Experimentos**"] + [f"- {t}" for t in L.experimentos]
    if L.cuidados:
        parts += ["**⚠️ Cuidados**"] + [f"- {t}" for t in L.cuidados]
    return "\n\n".join(parts[:2]) + "\n\n" + "\n".join(parts[2:]).replace("\n**", "\n\n**")


def static_quiz(cdef: CircuitDef, params: Optional[Dict[str, float]] = None, n: int = 3, seed: int = 0) -> List[Dict]:
    """Perguntas 'qual o valor de X?' com distratores ×2, ÷2, ×10, a partir da teoria do circuito."""
    rng = random.Random(seed)
    th = {k: v for k, v in cdef.theory_values(params).items() if v[0] not in (0, 1.0, 4.0) and v[1] != "1 = OK"}
    items = []
    for k, (val, unit) in rng.sample(list(th.items()), k=min(n, len(th))):
        wrong = [val * 2, val / 2, val * 10 if abs(val) < 1e6 else val / 10]
        opts = [val] + wrong
        rng.shuffle(opts)
        items.append({"pergunta": f"No circuito '{cdef.name}', quanto vale: {k}?",
                      "opcoes": [fmt(o, unit) for o in opts], "correta": opts.index(val),
                      "explicacao": f"Valor calculado pela fórmula do circuito: {fmt(val, unit)}."})
    return items
