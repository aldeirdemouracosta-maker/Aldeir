"""
CircuitSimulator – fachada sobre o motor ngspice (core.spice_engine).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .library.base import CircuitDef
from .spice_engine import (
    SanitizedNetlist, SpiceError, run_netlist, sanitize_netlist,
)


class CircuitSimulator:
    """Carrega um netlist (texto ou circuito da biblioteca) e roda análises."""

    def __init__(self, title: str = "CircuitForge Simulation"):
        self.title = title
        self.netlist: Optional[str] = None
        self.detected_analyses: List[str] = []
        self.warnings: List[str] = []
        self.last_result: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []

    # -- carregamento -------------------------------------------------
    def load_netlist(self, netlist: str, has_title: Optional[bool] = None) -> List[str]:
        """Carrega netlist SPICE em texto. Retorna avisos da sanitização."""
        from .library.base import HELPERS

        s: SanitizedNetlist = sanitize_netlist(netlist, default_title=self.title, has_title=has_title)
        self.title = s.title
        has_helpers = ".subckt opamp" in s.body.lower()
        body = s.body if has_helpers else HELPERS + s.body
        self.netlist = f"{s.title}\n{body}\n"
        self.detected_analyses = s.analyses
        self.warnings = s.warnings
        return s.warnings

    def load_circuit(self, cdef: CircuitDef, params: Optional[Dict[str, float]] = None) -> None:
        self.title = cdef.name
        self.load_netlist(cdef.netlist(params), has_title=True)

    # -- execução ------------------------------------------------------
    def run(self, analysis: Dict, timeout: float = 120.0) -> Dict[str, np.ndarray]:
        if self.netlist is None:
            raise RuntimeError("Nenhum circuito carregado.")
        data = run_netlist(self.netlist, analysis, timeout=timeout)
        kind = analysis["kind"]
        if kind == "ac":
            result: Dict[str, np.ndarray] = {"frequency": np.real(data.pop("frequency"))}
            for k, v in data.items():
                result[f"{k}_mag"] = np.abs(v)
                result[f"{k}_phase"] = np.angle(v, deg=True)
        elif kind == "op":
            result = {k: float(np.real(v[0])) for k, v in data.items()}
        else:
            result = {k: np.real(v) for k, v in data.items()}
            if kind == "dc":
                # primeira variável do .raw é o eixo varrido (v-sweep / nome da fonte)
                sweep_key = next(iter(data))
                result["sweep"] = np.real(data[sweep_key])
                result.pop(sweep_key, None)
        self.last_result = {"type": kind, "data": result}
        self.history.append(self.last_result)
        return result

    def run_transient(self, step_time: float = 1e-6, end_time: float = 10e-3,
                      use_initial_condition: bool = False) -> Dict[str, np.ndarray]:
        return self.run({"kind": "tran", "step": step_time, "stop": end_time,
                         "maxstep": step_time, "uic": use_initial_condition})

    def run_ac(self, start_freq: float = 1.0, stop_freq: float = 1e6,
               points_per_decade: int = 20) -> Dict[str, np.ndarray]:
        return self.run({"kind": "ac", "start": start_freq, "stop": stop_freq,
                         "points": points_per_decade})

    def run_dc_sweep(self, component: str, start: float, stop: float, step: float):
        return self.run({"kind": "dc", "source": component, "start": start,
                         "stop": stop, "step": step})

    def run_operating_point(self) -> Dict[str, float]:
        return self.run({"kind": "op"})

    def get_last_result(self) -> Optional[Dict]:
        return self.last_result


__all__ = ["CircuitSimulator", "SpiceError"]
