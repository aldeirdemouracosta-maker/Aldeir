"""Validação de netlists (gerados pela IA ou escritos pelo usuário) rodando no ngspice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from core.simulator import CircuitSimulator
from core.spice_engine import SpiceError, sanitize_netlist


@dataclass
class ValidationResult:
    ok: bool
    message: str = ""
    analysis: Optional[Dict] = None
    nodes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    result: Optional[Dict[str, np.ndarray]] = None


def default_analysis_for(netlist_analyses: List[str]) -> Dict:
    """Escolhe uma análise razoável: usa o cartão do próprio netlist, se houver."""
    from .parsing import parse_si
    for card in netlist_analyses:
        t = card.lower().split()
        try:
            if t[0] == ".tran":
                step, stop = parse_si(t[1]), parse_si(t[2])
                return {"kind": "tran", "step": step, "stop": stop, "maxstep": step}
            if t[0] == ".ac":
                return {"kind": "ac", "start": parse_si(t[3]), "stop": parse_si(t[4]), "points": int(t[2])}
            if t[0] == ".dc":
                return {"kind": "dc", "source": t[1], "start": parse_si(t[2]), "stop": parse_si(t[3]), "step": parse_si(t[4])}
            if t[0] == ".op":
                return {"kind": "op"}
        except (ValueError, IndexError):
            continue
    return {"kind": "tran", "step": 10e-6, "stop": 10e-3, "maxstep": 10e-6}


def validate_netlist(netlist: str, analysis: Optional[Dict] = None, probes: Optional[List[str]] = None,
                     timeout: float = 30.0) -> ValidationResult:
    """Sanitiza, simula e confere sanidade (valores finitos, sondas existentes, circuito não trivial)."""
    try:
        san = sanitize_netlist(netlist)
    except SpiceError as e:
        return ValidationResult(False, f"Netlist recusado: {e}")
    if analysis is None:
        analysis = default_analysis_for(san.analyses)
    sim = CircuitSimulator()
    try:
        sim.load_netlist(netlist)
        res = sim.run(analysis, timeout=timeout)
    except SpiceError as e:
        return ValidationResult(False, str(e), analysis, warnings=san.warnings)
    except Exception as e:  # noqa: BLE001
        return ValidationResult(False, f"Erro inesperado: {e}", analysis, warnings=san.warnings)

    nodes = [k for k in res if k not in ("time", "frequency", "sweep") and "." not in k and not k.startswith("i(")
             and not k.endswith(("_mag", "_phase"))]
    if analysis["kind"] == "ac":
        nodes = sorted({k[:-4] for k in res if k.endswith("_mag") and "." not in k and not k.startswith("i(")})
    bad = [k for k, v in res.items() if not np.all(np.isfinite(np.atleast_1d(v)))]
    if bad:
        return ValidationResult(False, f"Valores não finitos em: {', '.join(bad[:4])}", analysis, nodes, san.warnings)
    if not nodes:
        return ValidationResult(False, "O circuito não produziu nenhum nó de saída.", analysis, nodes, san.warnings)
    missing = [p for p in (probes or []) if p not in nodes]
    if missing:
        return ValidationResult(False, f"Sondas inexistentes: {', '.join(missing)}. Nós disponíveis: {', '.join(nodes[:12])}",
                                analysis, nodes, san.warnings)
    flat = True
    for k in nodes[:8]:
        v = np.atleast_1d(res.get(k, res.get(f"{k}_mag", [0.0])))
        if np.ptp(v) > 1e-9 or abs(v[0]) > 1e-9:
            flat = False
    if flat:
        return ValidationResult(False, "Todos os nós ficaram em 0 V: falta uma fonte de tensão/corrente ou ligação ao nó 0.",
                                analysis, nodes, san.warnings)
    return ValidationResult(True, "Netlist válido.", analysis, nodes, san.warnings, res)
