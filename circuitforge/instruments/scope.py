"""
Osciloscópio virtual – formas de onda no tempo com medições automáticas.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import plotly.graph_objects as go

from .spectrum import thd as _thd

COLORS = ["#00E5FF", "#FF6B6B", "#4ECDC4", "#FFE66D", "#C44DFF", "#95E1D3"]


def visible_channels(result: Dict[str, np.ndarray], include_currents: bool = False,
                     include_internal: bool = False) -> List[str]:
    """Nomes de canais úteis (oculta o interior de subcircuitos e, opcionalmente, correntes)."""
    out = []
    for k, v in result.items():
        if k in ("time", "frequency", "sweep") or not isinstance(v, np.ndarray) or v.ndim != 1:
            continue
        if not include_internal and ("." in k):
            continue
        if not include_currents and k.startswith("i("):
            continue
        out.append(k)
    return out


class Oscilloscope:
    def __init__(self, title: str = "Osciloscópio Virtual"):
        self.title = title
        self.channels: Dict[str, np.ndarray] = {}
        self.time: Optional[np.ndarray] = None

    def load(self, result: Dict[str, np.ndarray], time_key: str = "time") -> None:
        self.time = result.get(time_key)
        self.channels = {k: v for k, v in result.items()
                         if k != time_key and isinstance(v, np.ndarray) and v.ndim == 1}

    def plot(self, channels: Optional[List[str]] = None, time_unit: str = "ms",
             voltage_unit: str = "V", height: int = 500, x_range: Optional[tuple] = None) -> go.Figure:
        if self.time is None or not self.channels:
            fig = go.Figure()
            fig.add_annotation(text="Nenhum dado carregado", showarrow=False)
            return fig
        scale = {"s": 1.0, "ms": 1e3, "us": 1e6, "ns": 1e9, "ps": 1e12}.get(time_unit, 1e3)
        t = self.time * scale
        channels = channels if channels is not None else visible_channels(self.channels)
        fig = go.Figure()
        for i, ch in enumerate(channels):
            if ch in self.channels:
                fig.add_trace(go.Scattergl(x=t, y=self.channels[ch], mode="lines", name=ch,
                                           line=dict(color=COLORS[i % len(COLORS)], width=2)))
        fig.update_layout(title=self.title, xaxis_title=f"Tempo ({time_unit})",
                          yaxis_title=f"Amplitude ({voltage_unit})", template="plotly_dark", height=height,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02),
                          margin=dict(l=60, r=30, t=60, b=50), hovermode="x unified")
        if x_range:
            fig.update_xaxes(range=list(x_range))
        fig.update_xaxes(showgrid=True, gridcolor="#333")
        fig.update_yaxes(showgrid=True, gridcolor="#333")
        return fig

    # ------------------------------------------------------------------
    def measure(self, channel: str, settle_fraction: float = 0.4) -> Dict[str, float]:
        """
        Medições na parte final do sinal (descarta `settle_fraction` inicial para ignorar
        o transitório de partida). Frequência por cruzamentos ascendentes da média.
        """
        if channel not in self.channels or self.time is None:
            return {}
        t_all, y_all = self.time, self.channels[channel]
        sel = t_all >= t_all[0] + (t_all[-1] - t_all[0]) * settle_fraction
        t, y = t_all[sel], y_all[sel]
        if len(y) < 4:
            t, y = t_all, y_all
        vavg = float(np.mean(y))
        yac = y - vavg
        freq = 0.0
        up = np.where((yac[:-1] < 0) & (yac[1:] >= 0))[0]
        if len(up) >= 2:
            tc = t[up] + (0 - yac[up]) * (t[up + 1] - t[up]) / (yac[up + 1] - yac[up] + 1e-30)
            freq = float(1.0 / np.mean(np.diff(tc)))
        return {
            "Vpp": float(np.ptp(y)), "Vmax": float(np.max(y)), "Vmin": float(np.min(y)),
            "Vavg": vavg, "Vrms": float(np.sqrt(np.mean(y ** 2))),
            "Vrms_AC": float(np.sqrt(np.mean(yac ** 2))), "Freq_Hz": freq,
            "Ripple_pp": float(np.ptp(y)),
        }

    def thd(self, channel: str, f0: Optional[float] = None) -> Dict[str, float]:
        if channel not in self.channels or self.time is None:
            return {}
        return _thd(self.time, self.channels[channel], f0)
