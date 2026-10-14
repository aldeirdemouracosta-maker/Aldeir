"""Leitura das respostas do LLM (netlist em bloco de código + metadados)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from core.units import parse_si  # noqa: F401  (reexportado)


def parse_analysis(line: str) -> Optional[Dict]:
    """'tran stop=5m step=5u' | 'ac start=10 stop=1e6' | 'dc src=Vin start=0 stop=5 step=0.1' | 'op'."""
    if not line:
        return None
    toks = line.strip().replace(",", " ").split()
    if not toks:
        return None
    kind = toks[0].lower().lstrip(".")
    kv: Dict[str, str] = {}
    for t in toks[1:]:
        if "=" in t:
            k, v = t.split("=", 1)
            kv[k.lower()] = v
    try:
        if kind == "op":
            return {"kind": "op"}
        if kind in ("tran", "transient"):
            stop = parse_si(kv.get("stop", kv.get("fim", "10m")))
            step = parse_si(kv["step"]) if "step" in kv else stop / 2000
            step = max(step, stop / 200000)
            return {"kind": "tran", "step": step, "stop": stop, "maxstep": step}
        if kind == "ac":
            return {"kind": "ac", "start": parse_si(kv.get("start", "10")), "stop": parse_si(kv.get("stop", "1meg")),
                    "points": int(float(kv.get("points", 20)))}
        if kind == "dc":
            src = kv.get("src", kv.get("source", "Vin"))
            return {"kind": "dc", "source": src, "start": parse_si(kv.get("start", "0")),
                    "stop": parse_si(kv.get("stop", "5")), "step": parse_si(kv.get("step", "0.1"))}
    except (ValueError, KeyError):
        return None
    return None


def parse_creator_response(text: str) -> Dict:
    """
    Extrai {titulo, analise(str), sondas(list), netlist, explicacao} de uma resposta com campos
    TITULO:, ANALISE:, SONDAS:, bloco ```spice ... ``` e EXPLICACAO:.
    Aceita também o netlist cru (sem cerca) quando o modelo pequeno esquece o bloco.
    """
    out: Dict = {"titulo": "", "analise": "", "sondas": [], "netlist": "", "explicacao": ""}
    t = text.replace("\r", "")
    m = re.search(r"^\s*T[ÍI]TULO\s*:\s*(.+)$", t, re.I | re.M)
    if m:
        out["titulo"] = m.group(1).strip()
    m = re.search(r"^\s*AN[ÁA]LISE\s*:\s*(.+)$", t, re.I | re.M)
    if m:
        out["analise"] = m.group(1).strip()
    m = re.search(r"^\s*SONDAS?\s*:\s*(.+)$", t, re.I | re.M)
    if m:
        out["sondas"] = [s.strip().lower() for s in re.split(r"[,; ]+", m.group(1)) if s.strip()]
    block = re.search(r"```(?:spice|spice3|ngspice|cir|netlist|text)?\s*\n(.*?)```", t, re.S | re.I)
    if block:
        out["netlist"] = block.group(1).strip()
    else:
        # sem cerca: pega linhas que parecem netlist (elementos/cartões) depois dos metadados
        lines = [ln for ln in t.split("\n")
                 if re.match(r"^\s*([A-Za-z][A-Za-z0-9_]*\s+\S+\s+\S+.*|\.[A-Za-z]+.*|\*.*)$", ln)
                 and not re.match(r"^\s*(T[ÍI]TULO|AN[ÁA]LISE|SONDAS?|EXPLICA)", ln, re.I)]
        out["netlist"] = "\n".join(lines).strip()
    m = re.search(r"EXPLICA[ÇC][ÃA]O\s*:\s*(.+)", t, re.I | re.S)
    if m:
        out["explicacao"] = re.split(r"```", m.group(1))[0].strip()
    return out
