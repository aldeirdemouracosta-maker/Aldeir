"""
CircuitSimulator – simulação SPICE via ngspice (modo batch).

O PySpice é usado apenas para *montar* circuitos; a execução é feita pelo
executor em `ngspice_runner` (compatível com ngspice 42+).
"""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Any
import numpy as np

from .ngspice_runner import run_ngspice, normalize_names, NgSpiceError


class _TextCircuit:
    """Circuito baseado em texto (netlist SPICE puro)."""

    def __init__(self, text: str):
        self.text = text

    def __str__(self) -> str:
        return self.text


class CircuitSimulator:
    """
    Motor de simulação SPICE para o CircuitForge.
    Suporta DC (ponto de operação e varredura), AC e Transient.
    """

    def __init__(self, title: str = "CircuitForge Simulation"):
        self.title = title
        self.circuit: Optional[Any] = None
        self.last_result = None
        self.history: List[Dict[str, Any]] = []

    def new_circuit(self, title: Optional[str] = None):
        try:
            from PySpice.Spice.Netlist import Circuit
        except ImportError as exc:
            raise ImportError("PySpice não está instalado. Execute: pip install PySpice") from exc
        self.circuit = Circuit(title or self.title)
        return self.circuit

    def load_netlist(self, netlist: str) -> None:
        """Carrega um netlist SPICE puro (texto)."""
        if not netlist or not netlist.strip():
            raise ValueError("Netlist vazio.")
        text = netlist.strip()
        if text.startswith("*") or text.startswith("."):
            # sem linha de título explícita: adiciona uma
            if not text.lower().startswith(".title"):
                text = f"{self.title}\n{text}"
        self.circuit = _TextCircuit(text)

    def _netlist(self) -> str:
        if self.circuit is None:
            raise RuntimeError("Nenhum circuito definido.")
        return str(self.circuit)

    def _record(self, kind: str, data: Dict) -> Dict:
        self.last_result = {"type": kind, "data": data}
        self.history.append(self.last_result)
        return data

    def run_transient(
        self,
        step_time: float = 1e-6,
        end_time: float = 10e-3,
        use_initial_condition: bool = False,
    ) -> Dict[str, np.ndarray]:
        """Simulação no domínio do tempo."""
        card = f".tran {step_time:.6g} {end_time:.6g}" + (" uic" if use_initial_condition else "")
        raw = run_ngspice(self._netlist(), card)
        nodes, branches = normalize_names(raw)
        result = {"time": np.real(raw["time"])}
        for k, v in {**nodes, **branches}.items():
            result[k] = np.real(v)
        return self._record("transient", result)

    def run_ac(
        self,
        start_freq: float = 1.0,
        stop_freq: float = 1e6,
        points_per_decade: int = 10,
        variation: str = "dec",
    ) -> Dict[str, np.ndarray]:
        """Análise AC (Bode). As fontes precisam ter magnitude AC (veja `ensure_ac_source`)."""
        netlist = ensure_ac_source(self._netlist())
        card = f".ac {variation} {int(points_per_decade)} {start_freq:.6g} {stop_freq:.6g}"
        raw = run_ngspice(netlist, card)
        nodes, _ = normalize_names(raw)
        result = {"frequency": np.real(raw["frequency"])}
        for node, v in nodes.items():
            v = np.asarray(v)
            result[f"{node}_mag"] = np.abs(v)
            result[f"{node}_phase"] = np.angle(v, deg=True)
        return self._record("ac", result)

    def run_dc_sweep(
        self,
        component: str,
        start: float,
        stop: float,
        step: float,
    ) -> Dict[str, np.ndarray]:
        """Varredura DC de uma fonte (ex: 'Vin' ou 'VVin')."""
        netlist = self._netlist()
        src = _resolve_source(netlist, component)
        card = f".dc {src} {start:.6g} {stop:.6g} {step:.6g}"
        raw = run_ngspice(netlist, card)
        nodes, branches = normalize_names(raw)
        sweep_key = next((k for k in raw if k.lower().endswith("-sweep") or k.lower() == src.lower()), None)
        result = {k: np.real(v) for k, v in {**nodes, **branches}.items()}
        result["sweep"] = np.real(raw[sweep_key]) if sweep_key else np.arange(start, stop + step / 2, step)
        return self._record("dc_sweep", result)

    def run_operating_point(self) -> Dict[str, float]:
        """Ponto de operação DC."""
        raw = run_ngspice(self._netlist(), ".op")
        nodes, branches = normalize_names(raw)
        result = {k: float(np.real(v[0])) for k, v in {**nodes, **branches}.items()}
        return self._record("op", result)

    def get_last_result(self) -> Optional[Dict]:
        return self.last_result


def _resolve_source(netlist: str, name: str) -> str:
    """Acha o nome real da fonte no netlist (aceita 'Vin' para 'VVin')."""
    names = [ln.split()[0] for ln in netlist.splitlines() if ln.strip() and ln[0] in "VvIi"]
    for cand in (name, "V" + name, "I" + name):
        for n in names:
            if n.lower() == cand.lower():
                return n
    raise ValueError(f"Fonte '{name}' não encontrada no netlist (disponíveis: {names}).")


def ensure_ac_source(netlist: str) -> str:
    """Se nenhuma fonte tiver `AC`, marca as fontes senoidais/DC de entrada com AC 1."""
    lines = netlist.splitlines()
    if any(re.search(r"\bac\s+[-+0-9.]", ln, re.I) for ln in lines if ln[:1] in "VvIi"):
        return netlist
    out, done = [], False
    for ln in lines:
        if not done and ln[:1] in "Vv" and re.match(r"^\S+\s+\S+\s+\S+\s+sin", ln, re.I):
            ln += " AC 1"
            done = True
        out.append(ln)
    if not done:  # fallback: primeira fonte de tensão que não seja alimentação
        for i, ln in enumerate(out):
            if ln[:1] in "Vv" and not re.search(r"vcc|vdd|vbat|vbus", ln.split()[0], re.I):
                out[i] = ln + " AC 1"
                done = True
                break
    return "\n".join(out)
