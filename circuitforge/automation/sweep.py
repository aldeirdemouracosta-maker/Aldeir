"""Varredura de parâmetros (Parameter Sweep) sobre circuitos da biblioteca ou netlists livres."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from core.library.base import CircuitDef
from core.simulator import CircuitSimulator
from core.spice_engine import SpiceError


class ParameterSweep:
    """
    Varre UM parâmetro de um ``CircuitDef`` aplicando-o de verdade ao circuito.
    (Corrige a versão anterior, em que o valor nunca chegava ao circuito.)
    """

    def __init__(self, circuit: CircuitDef, base_params: Optional[Dict[str, float]] = None):
        self.circuit = circuit
        self.base = circuit.resolve(base_params)
        self.results: List[Dict[str, Any]] = []

    def run(self, param: str, values: List[float], analysis: Optional[str] = None,
            measure_fn: Optional[Callable[[Dict], Dict]] = None, keep_results: bool = False,
            progress: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame:
        if param not in self.base:
            raise KeyError(f"Parâmetro desconhecido: {param}")
        rows = []
        self.results = []
        for idx, v in enumerate(values):
            if progress:
                progress(idx, len(values))
            params = {**self.base, param: float(v)}
            sim = CircuitSimulator()
            sim.load_circuit(self.circuit, params)
            opts = self.circuit.analysis_options(params)
            spec = opts[analysis] if analysis else next(iter(opts.values()))
            row: Dict[str, Any] = {param: float(v)}
            try:
                res = sim.run(spec)
                row.update(measure_fn(res) if measure_fn else {})
                if keep_results:
                    self.results.append({"value": v, "result": res})
            except SpiceError as e:
                row["erro"] = str(e)[:120]
            rows.append(row)
        return pd.DataFrame(rows)

    # compatibilidade com a API anterior
    def sweep_transient(self, param_name, values, measure_fn=None, **_):
        return self.run(param_name, values, measure_fn=measure_fn)

    def sweep_ac(self, param_name, values, measure_fn=None, **_):
        return self.run(param_name, values, measure_fn=measure_fn)
