"""
Varredura de parâmetros (Parameter Sweep).
"""

from __future__ import annotations
from typing import Dict, List, Callable, Any, Optional
import numpy as np
import pandas as pd
from copy import deepcopy


class ParameterSweep:
    """
    Executa múltiplas simulações variando um ou mais parâmetros.
    Ideal para caracterização de circuitos e otimização.
    """

    def __init__(self, simulator_factory: Callable[..., Any]):
        """
        simulator_factory: função `factory(value) -> CircuitSimulator` que monta
                           o circuito com o parâmetro varrido igual a `value`.
                           (Factory sem argumentos também é aceita, mas então
                           o valor varrido não afeta o circuito.)
        """
        self.factory = simulator_factory
        self.results: List[Dict[str, Any]] = []

    def _make(self, value: float) -> Any:
        import inspect
        try:
            takes_arg = len(inspect.signature(self.factory).parameters) > 0
        except (TypeError, ValueError):
            takes_arg = True
        return self.factory(value) if takes_arg else self.factory()

    def sweep_transient(
        self,
        param_name: str,
        values: List[float],
        step_time: float = 1e-6,
        end_time: float = 10e-3,
        measure_fn: Optional[Callable[[Dict], Dict]] = None,
    ) -> pd.DataFrame:
        """
        Varre um parâmetro e roda simulação transient para cada valor.
        measure_fn: função opcional que recebe o resultado e retorna métricas.
        """
        rows = []
        for val in values:
            sim = self._make(val)
            result = sim.run_transient(step_time=step_time, end_time=end_time)
            metrics = measure_fn(result) if measure_fn else {}
            row = {param_name: val, **metrics}
            rows.append(row)
            self.results.append({"param": param_name, "value": val, "result": result})

        return pd.DataFrame(rows)

    def sweep_ac(
        self,
        param_name: str,
        values: List[float],
        start_freq: float = 1.0,
        stop_freq: float = 1e6,
        measure_fn: Optional[Callable[[Dict], Dict]] = None,
    ) -> pd.DataFrame:
        rows = []
        for val in values:
            sim = self._make(val)
            result = sim.run_ac(start_freq=start_freq, stop_freq=stop_freq)
            metrics = measure_fn(result) if measure_fn else {}
            row = {param_name: val, **metrics}
            rows.append(row)
            self.results.append({"param": param_name, "value": val, "result": result})
        return pd.DataFrame(rows)
