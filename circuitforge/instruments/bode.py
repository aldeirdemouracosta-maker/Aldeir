"""Analisador de Bode (magnitude + fase) e de casamento RF (|Γ|, ROE, perda de retorno)."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS = ["#00E5FF", "#FF6B6B", "#4ECDC4", "#FFE66D", "#C44DFF"]


class BodePlotter:
    def __init__(self, title: str = "Diagrama de Bode"):
        self.title = title
        self.frequency: Optional[np.ndarray] = None
        self.mag: Dict[str, np.ndarray] = {}
        self.phase: Dict[str, np.ndarray] = {}

    def load(self, result: Dict[str, np.ndarray], freq_key: str = "frequency") -> None:
        self.frequency = result.get(freq_key)
        self.mag, self.phase = {}, {}
        for k, v in result.items():
            if k.endswith("_mag"):
                self.mag[k[:-4]] = v
            elif k.endswith("_phase"):
                self.phase[k[:-6]] = v

    def channels(self) -> List[str]:
        return [k for k in self.mag if "." not in k and not k.startswith("i(")]

    def plot(self, channels: Optional[List[str]] = None, height: int = 600) -> go.Figure:
        if self.frequency is None:
            fig = go.Figure()
            fig.add_annotation(text="Nenhum dado AC carregado", showarrow=False)
            return fig
        channels = channels if channels is not None else self.channels()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Magnitude (dB)", "Fase (°)"),
                            vertical_spacing=0.08)
        for i, ch in enumerate(channels):
            color = COLORS[i % len(COLORS)]
            if ch in self.mag:
                fig.add_trace(go.Scatter(x=self.frequency, y=20 * np.log10(np.maximum(self.mag[ch], 1e-12)),
                                         mode="lines", name=ch, line=dict(color=color, width=2)), row=1, col=1)
            if ch in self.phase:
                fig.add_trace(go.Scatter(x=self.frequency, y=self.phase[ch], mode="lines", name=f"{ch} fase",
                                         line=dict(color=color, width=2, dash="dash"), showlegend=False), row=2, col=1)
        fig.update_xaxes(type="log", title_text="Frequência (Hz)", row=2, col=1)
        fig.update_xaxes(type="log", row=1, col=1)
        fig.update_yaxes(title_text="Magnitude (dB)", row=1, col=1)
        fig.update_yaxes(title_text="Fase (°)", row=2, col=1)
        fig.update_layout(title=self.title, template="plotly_dark", height=height,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02),
                          margin=dict(l=60, r=30, t=80, b=50), hovermode="x unified")
        return fig

    # ------------------------------------------------------------------
    def find_cutoff(self, channel: str, db_drop: float = -3.0) -> Optional[Dict[str, float]]:
        """
        Frequências de -3 dB em relação ao pico (passa-baixa, passa-alta ou passa-faixa).
        Retorna {'f_low', 'f_high', 'f_peak', 'type', 'peak_db'} (campos None quando não existem).
        """
        if channel not in self.mag or self.frequency is None:
            return None
        f = self.frequency
        db = 20 * np.log10(np.maximum(self.mag[channel], 1e-12))
        ipk = int(np.argmax(db))
        target = db[ipk] + db_drop

        def cross(rng):
            prev = None
            for i in rng:
                if db[i] <= target:
                    if prev is None:
                        return float(f[i])
                    # interpolação log-linear
                    x0, x1 = np.log10(f[prev]), np.log10(f[i])
                    y0, y1 = db[prev], db[i]
                    return float(10 ** (x0 + (target - y0) * (x1 - x0) / (y1 - y0))) if y1 != y0 else float(f[i])
                prev = i
            return None

        upper = cross(range(ipk, len(f)))
        lower = cross(range(ipk, -1, -1))
        if lower is None and upper is not None:
            kind = "passa-baixa"
        elif lower is not None and upper is None:
            kind = "passa-alta"
        elif lower is not None and upper is not None:
            kind = "passa-faixa"
        else:
            kind = "plano"
        return {"f_low": lower, "f_high": upper, "f_peak": float(f[ipk]), "peak_db": float(db[ipk]), "type": kind}


class RFAnalyzer:
    """Mostra |Γ|, perda de retorno e ROE (VSWR) a partir do nó 'gamma'."""

    def __init__(self, title: str = "Casamento de impedância"):
        self.title = title

    @staticmethod
    def vswr(gamma_mag: np.ndarray) -> np.ndarray:
        g = np.clip(gamma_mag, 0, 0.999999)
        return (1 + g) / (1 - g)

    def plot(self, result: Dict[str, np.ndarray], height: int = 520) -> go.Figure:
        f = result.get("frequency")
        g = result.get("gamma_mag")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("Perda de retorno (dB)", "ROE / VSWR"))
        if f is None or g is None:
            fig.add_annotation(text="Este circuito não possui nó 'gamma'", showarrow=False)
            return fig
        rl = -20 * np.log10(np.maximum(g, 1e-6))
        fig.add_trace(go.Scatter(x=f / 1e6, y=rl, mode="lines", name="RL", line=dict(color="#00E5FF", width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=f / 1e6, y=np.minimum(self.vswr(g), 20), mode="lines", name="ROE",
                                 line=dict(color="#FFE66D", width=2)), row=2, col=1)
        fig.add_hline(y=2, line_dash="dot", line_color="#888", row=2, col=1)
        fig.update_xaxes(title_text="Frequência (MHz)", row=2, col=1)
        fig.update_yaxes(title_text="dB", row=1, col=1)
        fig.update_yaxes(title_text="ROE", range=[1, 10], row=2, col=1)
        fig.update_layout(title=self.title, template="plotly_dark", height=height, showlegend=False,
                          margin=dict(l=60, r=30, t=70, b=50))
        return fig

    def summary(self, result: Dict[str, np.ndarray], max_vswr: float = 2.0) -> Dict[str, float]:
        f, g = result["frequency"], result["gamma_mag"]
        v = self.vswr(g)
        ok = v <= max_vswr
        out = {"f_melhor_casamento_Hz": float(f[np.argmin(g)]), "ROE_mínima": float(v.min()), "RL_máxima_dB": float(-20 * np.log10(max(g.min(), 1e-6)))}
        if ok.any():
            out["banda_ROE<=2_Hz"] = float(f[ok][-1] - f[ok][0])
        return out
