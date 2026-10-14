"""Métricas reutilizáveis para varreduras e Monte Carlo (recebem o dicionário de resultado)."""

from __future__ import annotations

from typing import Callable, Dict

import numpy as np


def _tail(y: np.ndarray, frac: float = 0.3) -> np.ndarray:
    return y[int(len(y) * (1 - frac)):]


def mean_tail(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"média({node})": float(np.mean(_tail(r[node])))}


def ripple_tail(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"ondulação({node})": float(np.ptp(_tail(r[node], 0.2)))}


def rms_tail(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"Vrms({node})": float(np.sqrt(np.mean(_tail(r[node]) ** 2)))}


def peak_tail(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"pico({node})": float(np.max(np.abs(_tail(r[node])))) }


def max_all(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"máx({node})": float(np.max(r[node]))}


def min_all(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"mín({node})": float(np.min(r[node]))}


def gain_db_at(node: str, freq: float) -> Callable[[Dict], Dict]:
    def fn(r):
        i = int(np.argmin(np.abs(r["frequency"] - freq)))
        return {f"ganho({node})@{freq:g}Hz [dB]": float(20 * np.log10(max(r[f'{node}_mag'][i], 1e-12)))}
    return fn


def peak_freq(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"f_pico({node}) [Hz]": float(r["frequency"][int(np.argmax(r[f'{node}_mag']))])}


def avg_power(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"P_média({node})": float(np.mean(_tail(r[node])))}


def max_value(node: str) -> Callable[[Dict], Dict]:
    return lambda r: {f"máx({node})": float(np.max(r[node]))}


METRICS = {
    "Valor médio (regime)": mean_tail,
    "Ondulação pico-a-pico (regime)": ripple_tail,
    "Valor RMS (regime)": rms_tail,
    "Pico absoluto (regime)": peak_tail,
    "Máximo": max_all,
    "Mínimo": min_all,
}
