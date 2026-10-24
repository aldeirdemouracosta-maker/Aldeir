"""
CircuitForge – Modificação de circuitos + análise por foto
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import base64


@dataclass
class ModificationResult:
    """Resultado de uma modificação proposta."""
    title: str
    description: str
    changes: List[str]
    original_label: str
    modified_label: str
    benefits: List[str]
    warnings: List[str]
    bom_add: List[str]
    bom_remove: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Amplificador de áudio – versões
# ---------------------------------------------------------------------------

def build_audio_amplifier_basic(
    gain: float = 10.0,
    vin_amplitude: float = 0.1,
    vin_freq: float = 1e3,
) -> Any:
    """
    Amplificador inversor simples (modelo op-amp).
    Ganho ≈ -Rf/Rin
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V, u_uF

    rin = 10e3
    rf = rin * gain

    circuit = Circuit("Audio Amplifier Basic")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.R("in", "in", "vneg", rin @ u_Ohm)
    circuit.R("f", "vneg", "out", rf @ u_Ohm)
    # Capacitor de acoplamento de entrada (bloqueia DC)
    circuit.C("in", "in_ac", "in", 10 @ u_uF)
    # Op-amp ideal (VCVS)
    circuit.VCVS("op", "out", circuit.gnd, circuit.gnd, "vneg", voltage_gain=1e5)
    # Carga
    circuit.R("load", "out", circuit.gnd, 8 @ u_Ohm)
    return circuit


def build_audio_amplifier_bass_boost(
    gain: float = 10.0,
    bass_boost_db: float = 6.0,
    vin_amplitude: float = 0.1,
    vin_freq: float = 100.0,
) -> Any:
    """
    Amplificador com reforço de graves (shelving simplificado via RC no feedback).
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V, u_uF, u_nF

    rin = 10e3
    rf = rin * gain

    circuit = Circuit("Audio Amplifier Bass Boost")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.C("in", "in_ac", "in", 10 @ u_uF)
    circuit.R("in", "in_ac", "vneg", rin @ u_Ohm)
    circuit.R("f", "vneg", "out", rf @ u_Ohm)
    # Rede de graves no feedback (aproximação)
    circuit.C("bass", "vneg", "bass_node", 22 @ u_nF)
    circuit.R("bass", "bass_node", "out", 4.7e3 @ u_Ohm)
    circuit.VCVS("op", "out", circuit.gnd, circuit.gnd, "vneg", voltage_gain=1e5)
    circuit.R("load", "out", circuit.gnd, 8 @ u_Ohm)
    return circuit


def build_audio_amplifier_with_battery(
    gain: float = 10.0,
    vbat: float = 7.4,
    vin_amplitude: float = 0.1,
    vin_freq: float = 1e3,
) -> Any:
    """
    Amplificador alimentado por bateria (modelo simplificado de 2S Li-ion / grafeno).
    Inclui regulador linear básico (representativo).
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V, u_uF

    rin = 10e3
    rf = rin * gain

    circuit = Circuit("Audio Amplifier + Battery Pack")
    # Bateria (fonte DC)
    circuit.V("Bat", "vbat", circuit.gnd, vbat @ u_V)
    # Regulador simplificado (queda fixa) → rail de 5V
    circuit.R("reg", "vbat", "vcc", 2 @ u_Ohm)  # perda representativa
    circuit.V("ref", "vcc", "vreg_sense", 5 @ u_V)  # placeholder
    # Sinal de áudio
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.C("in", "in_ac", "in", 10 @ u_uF)
    circuit.R("in", "in_ac", "vneg", rin @ u_Ohm)
    circuit.R("f", "vneg", "out", rf @ u_Ohm)
    circuit.VCVS("op", "out", circuit.gnd, circuit.gnd, "vneg", voltage_gain=1e5)
    circuit.R("load", "out", circuit.gnd, 8 @ u_Ohm)
    return circuit


# ---------------------------------------------------------------------------
# Catálogo de modificações prontas
# ---------------------------------------------------------------------------

MODIFICATION_PRESETS: Dict[str, Dict[str, Any]] = {
    "bass_boost": {
        "title": "Reforço de graves",
        "description": "Adiciona rede de realce de baixas frequências no feedback do amplificador.",
        "builder_original": build_audio_amplifier_basic,
        "builder_modified": build_audio_amplifier_bass_boost,
        "changes": [
            "Inserção de capacitor + resistor no caminho de feedback (shelving de graves)",
            "Ajuste do ponto de corte para enfatizar frequências < 200 Hz",
        ],
        "benefits": [
            "Graves mais presentes e encorpados",
            "Melhor percepção de volume em caixas pequenas",
        ],
        "warnings": [
            "Pode aumentar distorção se o alto-falante não aguentar o deslocamento",
            "Consumo ligeiramente maior em baixas frequências",
        ],
        "bom_add": ["C_bass 22nF", "R_bass 4.7kΩ"],
        "bom_remove": [],
    },
    "more_gain": {
        "title": "Aumento de volume / ganho",
        "description": "Aumenta o ganho do amplificador (mais volume).",
        "builder_original": lambda **kw: build_audio_amplifier_basic(gain=10, **{k: v for k, v in kw.items() if k != "gain"}),
        "builder_modified": lambda **kw: build_audio_amplifier_basic(gain=25, **{k: v for k, v in kw.items() if k != "gain"}),
        "changes": [
            "Aumento da relação Rf/Rin (ganho de 10× → 25×)",
            "Verificar margem de estabilidade e saturação",
        ],
        "benefits": [
            "Maior volume máximo",
            "Melhor aproveitamento de sinais fracos",
        ],
        "warnings": [
            "Risco de clipping se a alimentação for baixa",
            "Pode exigir fonte com mais corrente",
        ],
        "bom_add": ["Rf de valor maior (ex: 250kΩ)"],
        "bom_remove": ["Rf original"],
    },
    "graphene_battery": {
        "title": "Bateria recarregável (grafeno / Li-ion 2S)",
        "description": "Substitui a fonte fixa por pacote de bateria 7.4V com regulação básica.",
        "builder_original": build_audio_amplifier_basic,
        "builder_modified": build_audio_amplifier_with_battery,
        "changes": [
            "Adição de pacote 2S (7.4V nominal) – compatível com células de grafeno/Li-ion",
            "Regulador / caminho de alimentação para o estágio de áudio",
            "Acoplamento de entrada mantido",
        ],
        "benefits": [
            "Portabilidade (sem dependência de tomada)",
            "Possibilidade de carga rápida (grafeno)",
            "Operação em campo / outdoor",
        ],
        "warnings": [
            "Necessita circuito de carga e proteção (BMS) na versão real",
            "Autonomia depende da capacidade (mAh) das células",
            "Modelo atual é simplificado (não simula BMS completo)",
        ],
        "bom_add": [
            "Pacote 2S grafeno/Li-ion 7.4V",
            "Conector de carga",
            "BMS / proteção (recomendado)",
            "Regulador ou conversor buck (opcional)",
        ],
        "bom_remove": ["Fonte de alimentação fixa anterior"],
    },
}


def list_modification_presets() -> Dict[str, str]:
    return {k: v["title"] for k, v in MODIFICATION_PRESETS.items()}


def apply_preset(preset_id: str, **kwargs) -> Tuple[Any, Any, ModificationResult]:
    """
    Retorna (circuito_original, circuito_modificado, metadados).
    """
    if preset_id not in MODIFICATION_PRESETS:
        raise ValueError(f"Preset desconhecido: {preset_id}")

    p = MODIFICATION_PRESETS[preset_id]
    original = p["builder_original"](**kwargs)
    modified = p["builder_modified"](**kwargs)

    result = ModificationResult(
        title=p["title"],
        description=p["description"],
        changes=p["changes"],
        original_label="Original",
        modified_label=p["title"],
        benefits=p["benefits"],
        warnings=p["warnings"],
        bom_add=p["bom_add"],
        bom_remove=p["bom_remove"],
    )
    return original, modified, result


def image_to_base64(image_path: str | Path) -> str:
    """Converte imagem para base64 (para envio a modelos de visão)."""
    data = Path(image_path).read_bytes()
    return base64.b64encode(data).decode("utf-8")
