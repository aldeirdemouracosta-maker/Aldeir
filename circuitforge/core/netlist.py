"""
Construtores de circuitos de exemplo (PySpice) – a simulação roda via ngspice.
CircuitForge – EWB 2.0
"""

from __future__ import annotations
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Circuitos básicos R/C/L
# ---------------------------------------------------------------------------

def build_rc_lowpass(
    r_value: float = 1e3,
    c_value: float = 100e-9,
    vin_amplitude: float = 1.0,
    vin_freq: float = 1e3,
) -> Any:
    """Filtro RC passa-baixa clássico."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_F, u_Hz, u_V

    circuit = Circuit("RC Low-Pass Filter")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.R(1, "in", "out", r_value @ u_Ohm)
    circuit.C(1, "out", circuit.gnd, c_value @ u_F)
    return circuit


def build_rc_highpass(
    r_value: float = 1e3,
    c_value: float = 100e-9,
    vin_amplitude: float = 1.0,
    vin_freq: float = 1e3,
) -> Any:
    """Filtro RC passa-alta clássico."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_F, u_Hz, u_V

    circuit = Circuit("RC High-Pass Filter")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.C(1, "in", "out", c_value @ u_F)
    circuit.R(1, "out", circuit.gnd, r_value @ u_Ohm)
    return circuit


def build_rc_integrator(
    r_value: float = 1e3,
    c_value: float = 100e-9,
    vin_amplitude: float = 1.0,
    vin_freq: float = 100.0,
) -> Any:
    """Integrador RC passivo (aproximação em baixa frequência)."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_F, u_Hz, u_V

    circuit = Circuit("RC Integrator")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.R(1, "in", "out", r_value @ u_Ohm)
    circuit.C(1, "out", circuit.gnd, c_value @ u_F)
    return circuit


def build_rc_differentiator(
    r_value: float = 1e3,
    c_value: float = 100e-9,
    vin_amplitude: float = 1.0,
    vin_freq: float = 1e3,
) -> Any:
    """Diferenciador RC passivo (aproximação em alta frequência)."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_F, u_Hz, u_V

    circuit = Circuit("RC Differentiator")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.C(1, "in", "out", c_value @ u_F)
    circuit.R(1, "out", circuit.gnd, r_value @ u_Ohm)
    return circuit


def build_voltage_divider(
    r1: float = 10e3,
    r2: float = 10e3,
    vin: float = 5.0,
) -> Any:
    """Divisor de tensão resistivo."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_V

    circuit = Circuit("Voltage Divider")
    circuit.V("Vin", "in", circuit.gnd, vin @ u_V)
    circuit.R(1, "in", "out", r1 @ u_Ohm)
    circuit.R(2, "out", circuit.gnd, r2 @ u_Ohm)
    return circuit


def build_series_rlc(
    r_value: float = 50.0,
    l_value: float = 10e-3,
    c_value: float = 100e-9,
    vin_amplitude: float = 1.0,
    vin_freq: float = 5e3,
) -> Any:
    """Circuito RLC série (ressonância)."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_H, u_F, u_Hz, u_V

    circuit = Circuit("Series RLC Resonant")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.R(1, "in", "mid", r_value @ u_Ohm)
    circuit.L(1, "mid", "out", l_value @ u_H)
    circuit.C(1, "out", circuit.gnd, c_value @ u_F)
    return circuit


# ---------------------------------------------------------------------------
# Retificadores
# ---------------------------------------------------------------------------

def build_halfwave_rectifier(
    r_load: float = 1e3,
    vin_amplitude: float = 10.0,
    vin_freq: float = 60.0,
) -> Any:
    """Retificador de meia-onda com diodo ideal (modelo básico)."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V

    circuit = Circuit("Half-Wave Rectifier")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    # Diodo com modelo simples (Is, N)
    circuit.model("Dmod", "D", Is=1e-14, N=1.0)
    circuit.D(1, "in", "out", model="Dmod")
    circuit.R(1, "out", circuit.gnd, r_load @ u_Ohm)
    return circuit


def build_fullwave_bridge(
    r_load: float = 1e3,
    vin_amplitude: float = 10.0,
    vin_freq: float = 60.0,
) -> Any:
    """Retificador de onda completa em ponte (4 diodos)."""
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V

    circuit = Circuit("Full-Wave Bridge Rectifier")
    circuit.SinusoidalVoltageSource(
        "Vin", "ac1", "ac2",
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.model("Dmod", "D", Is=1e-14, N=1.0)
    # Ponte: ac1 -> D1 -> out+ ; ac2 -> D2 -> out+
    #        out- -> D3 -> ac1 ; out- -> D4 -> ac2
    circuit.D(1, "ac1", "outp", model="Dmod")
    circuit.D(2, "ac2", "outp", model="Dmod")
    circuit.D(3, "outn", "ac1", model="Dmod")
    circuit.D(4, "outn", "ac2", model="Dmod")
    circuit.R(1, "outp", "outn", r_load @ u_Ohm)
    # Referência de terra no lado negativo da carga
    circuit.R(2, "outn", circuit.gnd, 1 @ u_Ohm)  # sense
    return circuit


# ---------------------------------------------------------------------------
# Amplificadores (modelo comportamental / ideal)
# ---------------------------------------------------------------------------

def build_inverting_opamp(
    r_in: float = 10e3,
    r_f: float = 100e3,
    vin_amplitude: float = 0.1,
    vin_freq: float = 1e3,
    gain_ol: float = 1e5,
) -> Any:
    """
    Amplificador operacional inversor (modelo VCVS ideal com ganho finito).
    Ganho fechado ≈ -Rf/Rin
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V

    circuit = Circuit("Inverting Op-Amp")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    circuit.R("in", "in", "vneg", r_in @ u_Ohm)
    circuit.R("f", "vneg", "out", r_f @ u_Ohm)
    # VCVS: V(out) = gain_ol * (V(vpos) - V(vneg)) ; vpos = gnd
    circuit.VCVS("op", "out", circuit.gnd, circuit.gnd, "vneg", voltage_gain=gain_ol)
    return circuit


def build_noninverting_opamp(
    r1: float = 10e3,
    r2: float = 90e3,
    vin_amplitude: float = 0.1,
    vin_freq: float = 1e3,
    gain_ol: float = 1e5,
) -> Any:
    """
    Amplificador operacional não-inversor (modelo VCVS).
    Ganho fechado ≈ 1 + R2/R1
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_Hz, u_V

    circuit = Circuit("Non-Inverting Op-Amp")
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    # Divisor de feedback
    circuit.R(1, "out", "vneg", r2 @ u_Ohm)
    circuit.R(2, "vneg", circuit.gnd, r1 @ u_Ohm)
    # VCVS: entrada positiva = Vin, negativa = vneg
    circuit.VCVS("op", "out", circuit.gnd, "in", "vneg", voltage_gain=gain_ol)
    return circuit


def build_common_emitter(
    rb: float = 470e3,
    rc: float = 2e3,
    re: float = 200.0,
    vcc: float = 12.0,
    vin_amplitude: float = 0.01,
    vin_freq: float = 1e3,
) -> Any:
    """
    Amplificador emissor-comum com BJT NPN (modelo simples).
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_V, u_Hz, u_F

    circuit = Circuit("Common-Emitter Amplifier")
    circuit.V("Vcc", "vcc", circuit.gnd, vcc @ u_V)
    circuit.SinusoidalVoltageSource(
        "Vin", "in", circuit.gnd,
        amplitude=vin_amplitude @ u_V,
        frequency=vin_freq @ u_Hz,
    )
    # Polarização fixa via Rb a partir de Vcc; sinal entra por capacitor de acoplamento
    circuit.R("b", "vcc", "base", rb @ u_Ohm)
    circuit.C("in", "in", "base", 10e-6 @ u_F)
    circuit.R("c", "vcc", "collector", rc @ u_Ohm)
    circuit.R("e", "emitter", circuit.gnd, re @ u_Ohm)
    # Modelo BJT básico
    circuit.model("Qnpn", "NPN", Bf=100, Is=1e-14, Vaf=100)
    circuit.BJT(1, "collector", "base", "emitter", model="Qnpn")
    return circuit


def build_astable_555(
    r_a: float = 10e3,
    r_b: float = 10e3,
    c: float = 100e-9,
    vcc: float = 5.0,
) -> Any:
    """
    Oscilador 555 clássico (astável) com modelo comportamental.

    Os comparadores + flip-flop do 555 são equivalentes a chaves com histerese
    controladas pela tensão do capacitor: fecham acima de 2/3·Vcc e reabrem
    abaixo de 1/3·Vcc. Uma chave descarrega o capacitor (pino 7) e outra puxa
    a saída ("out") para baixo.  f ≈ 1.44 / ((Ra + 2·Rb)·C)
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_F, u_V

    circuit = Circuit("555 Astable Multivibrator")
    circuit.V("Vcc", "vcc", circuit.gnd, vcc @ u_V)
    circuit.R("Ra", "vcc", "discharge", r_a @ u_Ohm)
    circuit.R("Rb", "discharge", "threshold", r_b @ u_Ohm)
    circuit.C(1, "threshold", circuit.gnd, c @ u_F)
    # Pino 7 (descarga): conduz quando Vc > 2/3 Vcc, solta quando Vc < 1/3 Vcc
    circuit.model(
        "SW555", "SW",
        Vt=vcc / 2.0, Vh=vcc / 6.0, Ron=1.0, Roff=1e9,
    )
    circuit.S("dis", "discharge", circuit.gnd, "threshold", circuit.gnd, model="SW555")
    # Saída: alta enquanto carrega, baixa enquanto descarrega
    circuit.R("out_pu", "vcc", "out", 100 @ u_Ohm)
    circuit.S("out", "out", circuit.gnd, "threshold", circuit.gnd, model="SW555")
    return circuit


# ---------------------------------------------------------------------------
# Energia renovável / Biogás / Solar
# ---------------------------------------------------------------------------

def build_biodigester_control(
    setpoint_c: float = 37.0,
    ambient_c: float = 20.0,
    heater_power_w: float = 200.0,
) -> Any:
    """
    Controle térmico de biodigestor (modelo elétrico equivalente).
    - Sensor de temperatura (escala 10 mV/°C)
    - Aquecedor resistivo
    - Controlador on/off (comparador)
    - Driver do agitador (motor DC = R + L)
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_V, u_H

    circuit = Circuit("Biodigester Thermal + Agitator Control")
    circuit.V("Vcc", "vcc", circuit.gnd, 24 @ u_V)

    v_set = setpoint_c * 0.01
    circuit.V("Vset", "vset", circuit.gnd, v_set @ u_V)

    v_sense = ambient_c * 0.01
    circuit.V("Vsense", "vsense", circuit.gnd, v_sense @ u_V)

    # Termostato on/off: a chave liga o aquecedor enquanto Vsense < Vset (meio frio)
    circuit.model("SWheat", "SW", Vt=0.0, Vh=0.005, Ron=0.01, Roff=1e9)
    r_heat = (24.0 ** 2) / max(heater_power_w, 1.0)
    circuit.R("heater", "vcc", "heater_node", r_heat @ u_Ohm)
    circuit.S("heater", "heater_node", circuit.gnd, "vset", "vsense", model="SWheat")

    circuit.R("mot", "vcc", "mot_mid", 4 @ u_Ohm)
    circuit.L("mot", "mot_mid", "mot_out", 10e-3 @ u_H)
    circuit.R("mot_load", "mot_out", circuit.gnd, 8 @ u_Ohm)
    return circuit


def build_methane_compressor(
    supply_v: float = 48.0,
    motor_r: float = 2.0,
    motor_l: float = 15e-3,
) -> Any:
    """
    Driver de compressor de metano (motor DC + soft-start + sensoriamento).
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_V, u_H, u_uF

    circuit = Circuit("Methane Compressor Motor Driver")
    circuit.V("Vbus", "vbus", circuit.gnd, supply_v @ u_V)

    circuit.R("soft", "vbus", "motor_in", 0.5 @ u_Ohm)
    circuit.C("soft", "motor_in", circuit.gnd, 1000 @ u_uF)

    circuit.R("mot", "motor_in", "mot_mid", motor_r @ u_Ohm)
    circuit.L("mot", "mot_mid", "mot_out", motor_l @ u_H)

    circuit.R("shunt", "mot_out", "shunt_out", 0.05 @ u_Ohm)
    circuit.R("load", "shunt_out", circuit.gnd, 6 @ u_Ohm)

    circuit.R("mon1", "vbus", "vmon", 100e3 @ u_Ohm)
    circuit.R("mon2", "vmon", circuit.gnd, 10e3 @ u_Ohm)
    return circuit


def build_solar_mppt_charger(
    v_panel: float = 18.0,
    v_battery: float = 12.6,
) -> Any:
    """
    Controlador de carga solar simplificado (PWM / buck-like).
    Painel + indutor + bateria + sensores.
    """
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_Ohm, u_V, u_H, u_uF

    circuit = Circuit("Solar MPPT / PWM Charger")
    circuit.V("panel", "panel_oc", circuit.gnd, v_panel @ u_V)
    circuit.R("panel_rs", "panel_oc", "panel_out", 0.3 @ u_Ohm)

    circuit.L("buck", "panel_out", "switch_node", 100e-6 @ u_H)
    circuit.R("diode", "switch_node", circuit.gnd, 0.5 @ u_Ohm)
    circuit.C("out", "switch_node", circuit.gnd, 470 @ u_uF)

    circuit.V("bat", "bat_ideal", circuit.gnd, v_battery @ u_V)
    circuit.R("bat_esr", "switch_node", "bat_ideal", 0.05 @ u_Ohm)

    circuit.R("sense1", "switch_node", "vsense", 100e3 @ u_Ohm)
    circuit.R("sense2", "vsense", circuit.gnd, 20e3 @ u_Ohm)
    circuit.R("sys_load", "switch_node", circuit.gnd, 24 @ u_Ohm)
    return circuit


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def list_example_circuits() -> Dict[str, str]:
    return {
        "rc_lowpass": "Filtro RC passa-baixa",
        "rc_highpass": "Filtro RC passa-alta",
        "rc_integrator": "Integrador RC passivo",
        "rc_differentiator": "Diferenciador RC passivo",
        "voltage_divider": "Divisor de tensão resistivo",
        "series_rlc": "Circuito RLC série (ressonância)",
        "halfwave_rectifier": "Retificador de meia-onda",
        "fullwave_bridge": "Retificador de onda completa (ponte)",
        "inverting_opamp": "Amplificador inversor (op-amp)",
        "noninverting_opamp": "Amplificador não-inversor (op-amp)",
        "common_emitter": "Amplificador emissor-comum (BJT)",
        "astable_555": "Oscilador 555 (astável)",
        "biodigester_control": "Biodigestor – controle térmico + agitador",
        "methane_compressor": "Compressor de metano – driver de motor",
        "solar_mppt_charger": "Solar MPPT / carregador de bateria",
    }


def get_builder(name: str):
    """Retorna a função construtora pelo nome do circuito."""
    builders = {
        "rc_lowpass": build_rc_lowpass,
        "rc_highpass": build_rc_highpass,
        "rc_integrator": build_rc_integrator,
        "rc_differentiator": build_rc_differentiator,
        "voltage_divider": build_voltage_divider,
        "series_rlc": build_series_rlc,
        "halfwave_rectifier": build_halfwave_rectifier,
        "fullwave_bridge": build_fullwave_bridge,
        "inverting_opamp": build_inverting_opamp,
        "noninverting_opamp": build_noninverting_opamp,
        "common_emitter": build_common_emitter,
        "astable_555": build_astable_555,
        "biodigester_control": build_biodigester_control,
        "methane_compressor": build_methane_compressor,
        "solar_mppt_charger": build_solar_mppt_charger,
    }
    return builders.get(name)
