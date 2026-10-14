"""Análise Monte Carlo – tolerâncias de componentes sobre circuitos da biblioteca."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from core.library.base import CircuitDef
from core.simulator import CircuitSimulator
from core.spice_engine import SpiceError


class MonteCarlo:
    """
    Roda N simulações variando estatisticamente os parâmetros do circuito.
    ``tolerances``: fração relativa (0.05 = 5 %); distribuição normal (3σ = tolerância) ou uniforme.
    """

    def __init__(self, circuit: CircuitDef, base_params: Optional[Dict[str, float]] = None):
        self.circuit = circuit
        self.base = circuit.resolve(base_params)

    def run(self, tolerances: Dict[str, float], n_runs: int = 50, distribution: str = "normal",
            analysis: Optional[str] = None, measure_fn: Optional[Callable[[Dict], Dict]] = None,
            seed: Optional[int] = 42,
            progress: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        rows = []
        for i in range(n_runs):
            if progress:
                progress(i, n_runs)
            varied = {}
            for name, tol in tolerances.items():
                if name not in self.base or tol <= 0:
                    continue
                nom = self.base[name]
                if distribution == "normal":
                    v = rng.normal(nom, tol * abs(nom) / 3.0)
                else:
                    v = rng.uniform(nom * (1 - tol), nom * (1 + tol))
                varied[name] = float(v)
            params = {**self.base, **varied}
            sim = CircuitSimulator()
            sim.load_circuit(self.circuit, params)
            opts = self.circuit.analysis_options(params)
            spec = opts[analysis] if analysis else next(iter(opts.values()))
            row: Dict[str, Any] = {"run": i, **varied}
            try:
                res = sim.run(spec)
                row.update(measure_fn(res) if measure_fn else {})
            except SpiceError as e:
                row["erro"] = str(e)[:120]
            rows.append(row)
        return pd.DataFrame(rows)

    @staticmethod
    def summary(df: pd.DataFrame, metric_cols: List[str]) -> pd.DataFrame:
        return df[metric_cols].describe()
