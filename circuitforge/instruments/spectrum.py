"""Analisador de espectro (FFT) e medição de THD."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go


def resample_uniform(t: np.ndarray, y: np.ndarray, n: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, float]:
    """O ngspice devolve passos não uniformes; interpola para uma grade uniforme."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    if n is None:
        dt_min = np.min(np.diff(t[t > t[0]])) if len(t) > 2 else (t[-1] - t[0]) / max(len(t), 1)
        n = int(min(max((t[-1] - t[0]) / max(dt_min, 1e-18), 1024), 2 ** 18))
    tu = np.linspace(t[0], t[-1], n)
    return tu, np.interp(tu, t, y), (tu[1] - tu[0])


def compute_spectrum(t, y, window: str = "hann") -> Tuple[np.ndarray, np.ndarray]:
    """Retorna (frequências, amplitude de pico em V)."""
    tu, yu, dt = resample_uniform(t, y)
    yu = yu - np.mean(yu)
    w = np.hanning(len(yu)) if window == "hann" else np.ones(len(yu))
    spec = np.abs(np.fft.rfft(yu * w)) / (np.sum(w) / 2)
    freqs = np.fft.rfftfreq(len(yu), dt)
    return freqs, spec


def estimate_fundamental(freqs: np.ndarray, mag: np.ndarray, fmin: float = 0.0) -> float:
    sel = freqs > max(fmin, freqs[1] * 2)
    if not sel.any():
        return 0.0
    i = np.argmax(np.where(sel, mag, 0))
    return float(freqs[i])


def thd(t, y, f0: Optional[float] = None, harmonics: int = 9, skip_fraction: float = 0.5) -> Dict[str, float]:
    """
    THD = √(Σ Vₙ²)/V₁ usando um número inteiro de períodos da parte final do sinal
    (descarta a fração inicial para ignorar o transitório).
    """
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    start = t[0] + (t[-1] - t[0]) * skip_fraction
    sel = t >= start
    t, y = t[sel], y[sel]
    if len(t) < 16:
        return {"THD_percent": float("nan"), "f0": 0.0}
    if f0 is None:
        f, m = compute_spectrum(t, y)
        f0 = estimate_fundamental(f, m)
    if f0 <= 0:
        return {"THD_percent": float("nan"), "f0": 0.0}
    period = 1.0 / f0
    n_per = int((t[-1] - t[0]) / period)
    if n_per < 1:
        return {"THD_percent": float("nan"), "f0": f0}
    t_end = t[0] + n_per * period
    n = 8192
    tu = t[0] + np.arange(n) * (n_per * period / n)
    yu = np.interp(tu, t, y)
    yu = yu - yu.mean()
    spec = np.abs(np.fft.rfft(yu)) / (n / 2)
    h = lambda k: spec[k * n_per] if k * n_per < len(spec) else 0.0
    v1 = h(1)
    if v1 <= 0:
        return {"THD_percent": float("nan"), "f0": f0}
    harm = [h(k) for k in range(2, harmonics + 1)]
    return {"THD_percent": 100 * float(np.sqrt(np.sum(np.square(harm)))) / v1, "f0": f0,
            "V1_pk": float(v1), **{f"H{k}_pk": float(h(k)) for k in range(2, min(harmonics, 6) + 1)}}


class SpectrumAnalyzer:
    def __init__(self, title: str = "Analisador de Espectro"):
        self.title = title
        self.t: Optional[np.ndarray] = None
        self.channels: Dict[str, np.ndarray] = {}

    def load(self, result: Dict[str, np.ndarray]) -> None:
        self.t = result.get("time")
        self.channels = {k: v for k, v in result.items() if k != "time" and isinstance(v, np.ndarray) and v.ndim == 1}

    def plot(self, channel: str, fmax: Optional[float] = None, db: bool = True, height: int = 450,
             skip_fraction: float = 0.3) -> go.Figure:
        fig = go.Figure()
        if self.t is None or channel not in self.channels:
            fig.add_annotation(text="Nenhum dado carregado", showarrow=False)
            return fig
        t, y = self.t, self.channels[channel]
        sel = t >= t[0] + (t[-1] - t[0]) * skip_fraction
        f, m = compute_spectrum(t[sel], y[sel])
        if fmax:
            k = f <= fmax
            f, m = f[k], m[k]
        yv = 20 * np.log10(np.maximum(m, 1e-9)) if db else m
        fig.add_trace(go.Scatter(x=f, y=yv, mode="lines", name=channel, line=dict(color="#00E5FF", width=1.5)))
        fig.update_layout(title=f"{self.title} – {channel}", template="plotly_dark", height=height,
                          xaxis_title="Frequência (Hz)", yaxis_title="Amplitude (dBV)" if db else "Amplitude (V pico)",
                          margin=dict(l=60, r=30, t=60, b=50))
        return fig
