"""Decisões do Safety Guard: limites configuráveis + histerese.

Recebe uma ``Reading`` e devolve um nível. Não executa nada: quem age é
``actions.py``. Sensores indisponíveis nunca disparam limite numérico.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .sensors import Reading

LEVELS = ("normal", "atencao", "reduzir", "pausar", "critico")
NORMAL, ATENCAO, REDUZIR, PAUSAR, CRITICO = range(5)

# Padrões conservadores para RX 580 (Polaris). O firmware da placa só
# estrangula perto de ~94 °C na borda; paramos bem antes. Ajuste no JSON.
DEFAULT_CONFIG: Dict = {
    "limites": {
        "temp_edge_c": {"atencao": 75, "reduzir": 80, "pausar": 85, "critico": 90, "histerese": 5},
        "temp_hotspot_c": {"atencao": 90, "reduzir": 95, "pausar": 100, "critico": 105, "histerese": 5},
        "temp_mem_c": {"atencao": 85, "reduzir": 90, "pausar": 95, "critico": 100, "histerese": 5},
        "vram_pct": {"atencao": 85, "reduzir": 92, "histerese": 4},
        "power_pct_cap": {"atencao": 95, "reduzir": 102, "histerese": 5},
    },
    # Amostras consecutivas abaixo do limite (já com histerese) antes de rebaixar o nível.
    "amostras_para_rebaixar": 3,
    # Sem nenhuma temperatura legível: "atencao" (só avisa) ou "pausar".
    "sem_temperatura": "atencao",
    # Ventoinha parada com borda acima deste valor gera "atencao".
    "ventoinha_parada_acima_c": 70,
}


def load_config(path: Optional[str] = None) -> Dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        for key, value in user.items():
            if key == "limites":
                for metric, limits in value.items():
                    cfg["limites"].setdefault(metric, {}).update(limits)
            else:
                cfg[key] = value
    validate_config(cfg)
    return cfg


def validate_config(cfg: Dict) -> None:
    for metric, limits in cfg["limites"].items():
        values = [limits[n] for n in LEVELS[1:] if limits.get(n) is not None]
        if values != sorted(values):
            raise ValueError(f"limites de '{metric}' precisam ser crescentes: {limits}")
        if limits.get("histerese", 0) < 0:
            raise ValueError(f"histerese negativa em '{metric}'")
    if cfg["sem_temperatura"] not in ("atencao", "pausar"):
        raise ValueError("sem_temperatura deve ser 'atencao' ou 'pausar'")


def derived_values(reading: Reading) -> Dict[str, Optional[float]]:
    m = reading.metrics
    values = {k: m.get(k) for k in ("temp_edge_c", "temp_hotspot_c", "temp_mem_c")}
    used, total = m.get("vram_used_mib"), m.get("vram_total_mib")
    values["vram_pct"] = used * 100.0 / total if used is not None and total else None
    power, cap = m.get("power_w"), m.get("power_cap_w")
    values["power_pct_cap"] = power * 100.0 / cap if power is not None and cap else None
    return values


@dataclass
class Decision:
    level: int
    previous: int
    reasons: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return LEVELS[self.level]

    @property
    def changed(self) -> bool:
        return self.level != self.previous

    def to_dict(self) -> dict:
        return {"nivel": self.name, "anterior": LEVELS[self.previous], "motivos": list(self.reasons)}


class GuardPolicy:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or load_config()
        validate_config(self.config)
        self.metric_levels: Dict[str, int] = {}
        self.level = NORMAL
        self._below_count = 0

    def _metric_level(self, metric: str, value: float, limits: Dict) -> int:
        steps = [(i, limits[n]) for i, n in enumerate(LEVELS) if i > 0 and limits.get(n) is not None]
        hyst = float(limits.get("histerese", 0))
        current = self.metric_levels.get(metric, NORMAL)
        # Sobe imediatamente ao cruzar o limite.
        raw = NORMAL
        for idx, threshold in steps:
            if value >= threshold:
                raw = idx
        if raw >= current:
            return raw
        # Desce só quando o valor fica abaixo do limite atual menos a histerese.
        level = current
        while level > raw:
            threshold = dict(steps).get(level)
            if threshold is not None and value >= threshold - hyst:
                break
            level -= 1
        return level

    def evaluate(self, reading: Reading) -> Decision:
        previous = self.level
        if previous == CRITICO:
            return Decision(CRITICO, CRITICO, ["nível crítico já atingido; job deve permanecer encerrado"])

        reasons: List[str] = []
        target = NORMAL
        values = derived_values(reading)
        for metric, limits in self.config["limites"].items():
            value = values.get(metric)
            if value is None:
                self.metric_levels.pop(metric, None)
                continue
            lvl = self._metric_level(metric, value, limits)
            self.metric_levels[metric] = lvl
            if lvl > NORMAL:
                reasons.append(f"{metric}={value:.1f} → {LEVELS[lvl]}")
            target = max(target, lvl)

        temps = [values[k] for k in ("temp_edge_c", "temp_hotspot_c", "temp_mem_c")]
        if all(t is None for t in temps):
            lvl = PAUSAR if self.config["sem_temperatura"] == "pausar" else ATENCAO
            reasons.append("nenhum sensor de temperatura disponível")
            target = max(target, lvl)

        edge = values.get("temp_edge_c")
        fan = reading.metrics.get("fan_rpm")
        if fan is not None and fan == 0 and edge is not None and edge >= self.config["ventoinha_parada_acima_c"]:
            reasons.append(f"ventoinha a 0 RPM com borda a {edge:.1f} °C")
            target = max(target, ATENCAO)

        if target >= previous:
            self.level = target
            self._below_count = 0
        else:
            self._below_count += 1
            if self._below_count >= int(self.config["amostras_para_rebaixar"]):
                self.level = target
                self._below_count = 0
            else:
                reasons.append(
                    f"aguardando {self.config['amostras_para_rebaixar']} amostras estáveis para sair de {LEVELS[previous]}"
                )
        return Decision(self.level, previous, reasons)
