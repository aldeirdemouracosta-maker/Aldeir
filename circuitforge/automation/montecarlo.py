"""
Análise Monte Carlo – tolerâncias de componentes.
"""

from __future__ import annotations
from typing import Dict, List, Callable, Any, Optional, Tuple
import numpy as np
import pandas as pd


class MonteCarlo:
    """
    Roda N simulações com variação estatística dos componentes
    (distribuição normal ou uniforme).
    """

    def __init__(self, simulator_factory: Callable[[Dict[str, float]], Any]):
        """
        simulator_factory: função que recebe um dict de valores de componentes
                           e retorna um CircuitSimulator pronto.
        """
        self.factory = simulator_factory
        self.results: List[Dict[str, Any]] = []

    def run(
        self,
        nominal: Dict[str, float],
        tolerances: Dict[str, float],  # percentual (ex: 0.05 = 5%)
        n_runs: int = 100,
        distribution: str = "normal",  # ou "uniform"
        analysis: str = "transient",
        analysis_kwargs: Optional[Dict] = None,
        measure_fn: Optional[Callable[[Dict], Dict]] = None,
        seed: Optional[int] = 42,
    ) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        analysis_kwargs = analysis_kwargs or {}
        rows = []

        for i in range(n_runs):
            varied = {}
            for name, nom in nominal.items():
                tol = tolerances.get(name, 0.0)
                if distribution == "normal":
                    # 3-sigma ≈ tolerância
                    sigma = (tol * nom) / 3.0
                    varied[name] = float(rng.normal(nom, sigma))
                else:
                    delta = tol * nom
                    varied[name] = float(rng.uniform(nom - delta, nom + delta))

            sim = self.factory(varied)

            if analysis == "transient":
                result = sim.run_transient(**analysis_kwargs)
            elif analysis == "ac":
                result = sim.run_ac(**analysis_kwargs)
            elif analysis == "op":
                result = sim.run_operating_point()
            else:
                raise ValueError(f"Análise desconhecida: {analysis}")

            metrics = measure_fn(result) if measure_fn else {}
            row = {"run": i, **varied, **metrics}
            rows.append(row)
            self.results.append({"run": i, "params": varied, "result": result})

        return pd.DataFrame(rows)

    def summary(self, df: pd.DataFrame, metric_cols: List[str]) -> pd.DataFrame:
        """Estatísticas descritivas das métricas."""
        return df[metric_cols].describe()
