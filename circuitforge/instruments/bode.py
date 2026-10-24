"""
Analisador de Bode (magnitude + fase).
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class BodePlotter:
    """
    Instrumento virtual de diagrama de Bode.
    """

    def __init__(self, title: str = "Diagrama de Bode"):
        self.title = title
        self.frequency: Optional[np.ndarray] = None
        self.mag: Dict[str, np.ndarray] = {}
        self.phase: Dict[str, np.ndarray] = {}

    def load(self, result: Dict[str, np.ndarray], freq_key: str = "frequency") -> None:
        self.frequency = result.get(freq_key)
        self.mag = {}
        self.phase = {}
        for k, v in result.items():
            if k.endswith("_mag"):
                name = k[:-4]
                self.mag[name] = v
            elif k.endswith("_phase"):
                name = k[:-6]
                self.phase[name] = v

    def plot(
        self,
        channels: Optional[List[str]] = None,
        height: int = 600,
    ) -> go.Figure:
        if self.frequency is None:
            fig = go.Figure()
            fig.add_annotation(text="Nenhum dado AC carregado", showarrow=False)
            return fig

        if channels is None:
            channels = list(self.mag.keys())

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            subplot_titles=("Magnitude (dB)", "Fase (°)"),
            vertical_spacing=0.08,
        )

        colors = ["#00E5FF", "#FF6B6B", "#4ECDC4", "#FFE66D", "#C44DFF"]

        for i, ch in enumerate(channels):
            color = colors[i % len(colors)]
            if ch in self.mag:
                mag_db = 20 * np.log10(np.maximum(self.mag[ch], 1e-12))
                fig.add_trace(
                    go.Scatter(
                        x=self.frequency,
                        y=mag_db,
                        mode="lines",
                        name=f"{ch} mag",
                        line=dict(color=color, width=2),
                    ),
                    row=1, col=1,
                )
            if ch in self.phase:
                fig.add_trace(
                    go.Scatter(
                        x=self.frequency,
                        y=self.phase[ch],
                        mode="lines",
                        name=f"{ch} phase",
                        line=dict(color=color, width=2, dash="dash"),
                        showlegend=False,
                    ),
                    row=2, col=1,
                )

        fig.update_xaxes(type="log", title_text="Frequência (Hz)", row=2, col=1)
        fig.update_yaxes(title_text="Magnitude (dB)", row=1, col=1)
        fig.update_yaxes(title_text="Fase (°)", row=2, col=1)

        fig.update_layout(
            title=self.title,
            template="plotly_dark",
            height=height,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=60, r=30, t=80, b=50),
            hovermode="x unified",
        )
        return fig

    def find_cutoff(self, channel: str, db_drop: float = -3.0) -> Optional[float]:
        """Encontra a frequência de corte aproximada (-3 dB)."""
        if channel not in self.mag or self.frequency is None:
            return None
        mag_db = 20 * np.log10(np.maximum(self.mag[channel], 1e-12))
        # Referência: maior ganho (passa-baixa/passa-banda); interpola em log(f)
        max_db = np.max(mag_db)
        target = max_db + db_drop
        below = mag_db <= target
        if not below.any():
            return None
        peak = int(np.argmax(mag_db))
        # procura o primeiro cruzamento depois do pico; senão, antes do pico (passa-alta)
        after = np.where(below[peak:])[0]
        if len(after):
            i = peak + int(after[0])
            j = i - 1
        else:
            before = np.where(below[:peak])[0]
            i = int(before[-1])
            j = i + 1
        f1, f2 = self.frequency[j], self.frequency[i]
        m1, m2 = mag_db[j], mag_db[i]
        if m1 == m2:
            return float(f2)
        frac = (target - m1) / (m2 - m1)
        return float(10 ** (np.log10(f1) + frac * (np.log10(f2) - np.log10(f1))))
