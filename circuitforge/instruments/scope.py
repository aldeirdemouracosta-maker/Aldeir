"""
Osciloscópio virtual – visualização de formas de onda no tempo.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class Oscilloscope:
    """
    Instrumento virtual de osciloscópio.
    Recebe resultado de simulação transient e gera gráfico interativo.
    """

    def __init__(self, title: str = "Osciloscópio Virtual"):
        self.title = title
        self.channels: Dict[str, np.ndarray] = {}
        self.time: Optional[np.ndarray] = None

    def load(self, result: Dict[str, np.ndarray], time_key: str = "time") -> None:
        self.time = result.get(time_key)
        self.channels = {
            k: v for k, v in result.items()
            if k != time_key and isinstance(v, np.ndarray)
        }

    def plot(
        self,
        channels: Optional[List[str]] = None,
        time_unit: str = "ms",
        voltage_unit: str = "V",
        height: int = 500,
    ) -> go.Figure:
        if self.time is None or not self.channels:
            fig = go.Figure()
            fig.add_annotation(text="Nenhum dado carregado", showarrow=False)
            return fig

        # Conversão de unidade de tempo
        scale = {"s": 1.0, "ms": 1e3, "us": 1e6, "ns": 1e9}.get(time_unit, 1e3)
        t = self.time * scale

        if channels is None:
            channels = list(self.channels.keys())

        fig = go.Figure()
        colors = ["#00E5FF", "#FF6B6B", "#4ECDC4", "#FFE66D", "#C44DFF", "#95E1D3"]

        for i, ch in enumerate(channels):
            if ch not in self.channels:
                continue
            fig.add_trace(
                go.Scatter(
                    x=t,
                    y=self.channels[ch],
                    mode="lines",
                    name=ch,
                    line=dict(color=colors[i % len(colors)], width=2),
                )
            )

        fig.update_layout(
            title=self.title,
            xaxis_title=f"Tempo ({time_unit})",
            yaxis_title=f"Tensão ({voltage_unit})",
            template="plotly_dark",
            height=height,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=60, r=30, t=60, b=50),
            hovermode="x unified",
        )
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#333")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#333")

        return fig

    def measure(self, channel: str) -> Dict[str, float]:
        """Medições básicas: Vpp, Vmax, Vmin, RMS, frequência aproximada."""
        if channel not in self.channels or self.time is None:
            return {}

        y = self.channels[channel]
        t = self.time

        vpp = float(np.ptp(y))
        vmax = float(np.max(y))
        vmin = float(np.min(y))
        vrms = float(np.sqrt(np.mean(y ** 2)))
        vavg = float(np.mean(y))

        # Frequência aproximada via zero-crossings
        zero_crossings = np.where(np.diff(np.signbit(y - vavg)))[0]
        freq = 0.0
        if len(zero_crossings) > 2:
            periods = np.diff(t[zero_crossings[::2]])
            if len(periods) > 0:
                freq = 1.0 / np.mean(periods)

        return {
            "Vpp": vpp,
            "Vmax": vmax,
            "Vmin": vmin,
            "Vrms": vrms,
            "Vavg": vavg,
            "Freq_Hz": freq,
        }
