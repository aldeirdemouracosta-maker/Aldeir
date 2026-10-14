"""Conversão de/para notação de engenharia (SPICE): 4.7k, 100n, 1meg."""

from __future__ import annotations

import re

_SI = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


def parse_si(text: str) -> float:
    """'10k' → 1e4, '5m' → 5e-3, '1meg' → 1e6, '2.2u' → 2.2e-6, '1e6' → 1e6, '100Hz' → 100."""
    t = str(text).strip().lower().replace(",", ".")
    m = re.fullmatch(r"([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(meg|[tgkmunpfµ])?[a-zω°%/²]*", t)
    if not m:
        raise ValueError(f"Número inválido: {text!r}")
    return float(m.group(1)) * (_SI[m.group(2)] if m.group(2) else 1.0)


def to_si(x: float, digits: int = 4) -> str:
    """4700.0 → '4.7k'; 1e-7 → '100n'; 2 → '2'."""
    if x == 0:
        return "0"
    a = abs(x)
    for scale, p in ((1e12, "t"), (1e9, "g"), (1e6, "meg"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")):
        if a >= scale * 0.9999999:
            v = x / scale
            return f"{v:.{digits}g}{p}"
    return f"{x:.{digits}g}"
