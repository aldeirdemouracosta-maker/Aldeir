#!/usr/bin/env python3
"""Gera docs/CATALOGO.md a partir da biblioteca (rode após adicionar circuitos)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.library import CATEGORIES, by_category

lines = ["# Catálogo de circuitos", "", "_Gerado por `tools/gen_catalog.py`._", ""]
total = 0
for key, lst in by_category().items():
    lines += [f"## {CATEGORIES[key]} ({len(lst)})", "", "| Circuito | Descrição | Análises |", "|---|---|---|"]
    for c in lst:
        total += 1
        lines.append(f"| `{c.id}` **{c.name}** | {c.summary} | {', '.join(c.analysis_options())} |")
    lines.append("")
lines.insert(3, f"**{total} circuitos.**\n")
out = ROOT / "docs" / "CATALOGO.md"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8")
print(f"{total} circuitos → {out}")
