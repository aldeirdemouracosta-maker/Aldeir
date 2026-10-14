"""Placas de computador: VRM da CPU, LDOs, PDN, barramento I²C, reset e clock."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, tran_time
from .fontes import buck_netlist, ldo_netlist


@circuit(
    id="cpu_vrm", name="VRM de CPU – buck de 2 fases entrelaçadas (12 V → 1,1 V)", category="computador",
    summary="Duas fases defasadas de 180° dividem a corrente e reduzem a ondulação; degrau de carga de 4 A para 24 A.",
    params=[Param("vin", "Entrada", 12.0, "V", 5, 20), Param("vout", "Tensão do núcleo", 1.1, "V", 0.6, 3.3),
            Param("f", "Frequência por fase", 300e3, "Hz", 100e3, 1e6), Param("l", "Indutor por fase", 330e-9, "H", 50e-9, 5e-6),
            Param("c", "Capacitor de saída total", 470e-6, "F", 10e-6, 5e-3), Param("i1", "Corrente inicial", 4.0, "A", 0.5, 60),
            Param("i2", "Corrente após degrau", 24.0, "A", 0.5, 80)],
    analyses=lambda p: {"Degrau de carga": {"kind": "tran", "step": 1 / p["f"] / 100, "stop": 80 / p["f"], "maxstep": 1 / p["f"] / 100, "uic": True}},
    probes=["out", "sw0", "sw1"],
    theory=lambda p: {"D por fase": (p["vout"] / p["vin"], ""), "Corrente por fase (carga final)": (p["i2"] / 2, "A"),
                      "Ondulação por fase ΔIL": ((p["vin"] - p["vout"]) * (p["vout"] / p["vin"]) / (p["l"] * p["f"]), "A"),
                      "Frequência de ondulação na saída (2 fases)": (2 * p["f"], "Hz")},
    lesson=Lesson(objetivo="Entender por que placas-mãe têm várias fases de alimentação para a CPU.",
                  teoria=["A CPU pede centenas de ampères com tensão baixa. Várias fases em paralelo dividem a corrente (menos calor por indutor).",
                          "Com N fases defasadas de 360°/N a ondulação na saída cancela parcialmente e sua frequência é N·f."],
                  observe=["No degrau de carga a tensão afunda e se recupera: é o 'droop' que o controle real compensa.",
                           "Compare sw0 e sw1: pulsos defasados de meio período."],
                  experimentos=["Aumente C de saída e veja o afundamento diminuir.", "Reduza L para respostas mais rápidas (e mais ondulação)."],
                  cuidados=["Malha aberta: placas reais usam controlador PWM com realimentação e 'load-line'."]))
def cpu_vrm(p):
    return buck_netlist(p["vin"], p["vout"], p["f"], p["l"], p["c"], 0.002, 1.0, phases=2,
                        i_step=(p["i1"], p["i2"]), t_step=30 / p["f"], vdrop=p["i1"] * 0.003 / 2, sync=True)


def _ldo_params(vin, vout, i1, i2):
    return [Param("vin", "Entrada", vin, "V", 3, 30), Param("vout", "Saída", vout, "V", 1.5, 20),
            Param("i1", "Corrente inicial", i1, "A", 0.001, 1), Param("i2", "Corrente após degrau", i2, "A", 0.001, 1),
            Param("cout", "Capacitor de saída", 10e-6, "F", 1e-7, 1e-2)]


@circuit(
    id="usb_3v3_ldo", name="USB 5 V → 3,3 V (LDO de placa)", category="computador",
    summary="Regulador linear que alimenta microcontroladores e periféricos a partir da porta USB.",
    params=_ldo_params(5.0, 3.3, 0.05, 0.3),
    analyses=lambda p: {"Degrau de carga": tran_time(400e-6, 4000)}, probes=["out"],
    theory=lambda p: {"Dissipação (carga final)": ((p["vin"] - p["vout"]) * p["i2"], "W"),
                      "Eficiência": (p["vout"] / p["vin"], "")},
    lesson=Lesson(objetivo="Dimensionar um LDO e calcular seu aquecimento.",
                  teoria=["P = (Vin − Vout)·Iout; com 5 V → 3,3 V e 300 mA são 0,51 W: cuidado com o encapsulamento."],
                  observe=["O capacitor de saída define o afundamento no degrau."],
                  experimentos=["Aumente a corrente para 0,8 A e calcule a temperatura (Rθ ≈ 60 °C/W)."]))
def usb_ldo(p):
    return ldo_netlist(p["vin"], p["vout"], p["i1"], p["i2"], p["cout"], 150e-6)


@circuit(
    id="pdn_impedance", name="Impedância da rede de alimentação (PDN) com desacoplamento", category="computador",
    summary="Curva |Z| vista pelo chip: VRM, capacitores de bulk, MLCCs e capacitância do die.",
    params=[Param("nbulk", "Nº de capacitores de bulk (330 µF)", 4, "", 1, 20), Param("nmlcc", "Nº de MLCCs", 20, "", 1, 200),
            Param("cmlcc", "Capacitância de cada MLCC", 10e-6, "F", 1e-7, 1e-4), Param("dv", "Ondulação permitida", 0.03, "×Vcore", 0.005, 0.2),
            Param("di", "Degrau de corrente", 20.0, "A", 1, 100)],
    analyses=lambda p: {"Impedância (AC)": ac(1e3, 1e9, 30)}, probes=["die"],
    theory=lambda p: {"Impedância-alvo Zt = ΔV/ΔI": (p["dv"] * 1.0 / p["di"], "Ω")},
    lesson=Lesson(objetivo="Escolher quantidade e valores de capacitores de desacoplamento.",
                  teoria=["A PDN deve ter |Z| < Zt = (ΔV permitido)/(ΔI) em toda a banda.",
                          "Cada grupo de capacitores cobre uma faixa; entre eles surgem picos de anti-ressonância.",
                          "A indutância (ESL, vias, encapsulamento) limita a eficácia em altas frequências."],
                  observe=["Picos de impedância entre bulk/MLCC e entre MLCC/die."],
                  experimentos=["Dobre o nº de MLCCs: o vale se aprofunda e o pico se desloca.", "Mude a capacitância dos MLCCs."]))
def pdn(p):
    nb, nm = int(round(p["nbulk"])), int(round(p["nmlcc"]))
    return f"""Rv nv 0 0.0008
Lv nv nb 60n
Rbulk nb xb 0.008
Cbulk xb xb2 {330e-6*nb:.6g}
Lbulk xb2 0 {3e-9/nb:.6g}
Lbrd nb nm 400p
Rbrd nb nm 0.0003
Rmlcc nm xm {0.004/nm:.6g}
Cmlcc xm xm2 {p['cmlcc']*nm:.6g}
Lmlcc xm2 0 {0.6e-9/nm:.6g}
Lpkg nm die 80p
Rpkg nm die 0.0002
Rd die xd 0.0005
Cdie xd 0 50n
Iz 0 die DC 0 AC 1"""


@circuit(
    id="i2c_bus", name="Barramento I²C – resistor de pull-up e capacitância", category="computador",
    summary="Borda de subida RC limita a velocidade: tr(30–70 %) ≈ 0,847·Rp·Cb.",
    params=[Param("rp", "Pull-up Rp", 4.7e3, "Ω", 500, 1e5), Param("cb", "Capacitância do barramento", 100e-12, "F", 1e-12, 1e-9),
            Param("vdd", "Tensão", 3.3, "V", 1.8, 5.5)],
    analyses=lambda p: {"Transient": tran_time(12 * p["rp"] * p["cb"] + 2e-6, 3000)}, probes=["sda"],
    theory=lambda p: {"Tempo de subida 30–70 % (definição I²C)": (0.8473 * p["rp"] * p["cb"], "s"),
                      "Limite Fast-mode (300 ns)": (300e-9, "s"),
                      "Corrente com SDA em nível baixo": (p["vdd"] / p["rp"], "A")},
    lesson=Lesson(objetivo="Escolher o pull-up do I²C.",
                  teoria=["Linhas open-drain só puxam para baixo; o resistor sobe. A subida é uma exponencial com τ = Rp·Cb.",
                          "Rp pequeno = borda rápida, porém mais corrente quando o nível é baixo (limite de 3 mA)."],
                  observe=["Descida rápida (transistor) e subida lenta (RC)."],
                  experimentos=["Aumente Cb para 400 pF (limite do I²C) e veja tr > 300 ns."]))
def i2c(p):
    T = max(8 * p["rp"] * p["cb"], 1e-6)
    return f"""Vdd vdd 0 DC {p['vdd']}
Rp vdd sda {p['rp']}
Cb sda 0 {p['cb']}
Vdrv drv 0 PULSE(0 1 {T/4:.6e} 5n 5n {T/2:.6e} {T:.6e})
S1 sda 0 drv 0 SWM"""


@circuit(
    id="power_on_reset", name="Reset na energização (RC + Schmitt)", category="computador",
    summary="Mantém o processador em reset por RC·ln(...) após a tensão estabilizar.",
    params=[Param("r", "R", 100e3, "Ω", 1e3, 1e7), Param("c", "C", 100e-9, "F", 1e-9, 1e-4), Param("vdd", "Tensão", 3.3, "V", 1.8, 5.5)],
    analyses=lambda p: {"Transient": tran_time(5 * p["r"] * p["c"], 3000)}, probes=["rc", "reset_n"],
    theory=lambda p: {"Atraso até 70 % de Vdd = 1,2·R·C": (-p["r"] * p["c"] * math.log(1 - 0.7), "s")},
    lesson=Lesson(objetivo="Garantir inicialização limpa de uma placa.",
                  teoria=["O capacitor carrega pelo resistor; a saída libera o reset quando ultrapassa o limiar do comparador (70 % Vdd)."],
                  observe=["reset_n sobe só depois de RC·1,2."],
                  experimentos=["Dobre C e confirme o atraso dobrado."]))
def por(p):
    return f"""Vdd vdd 0 PULSE(0 {p['vdd']} 50u 100u 1u 1 2)
R1 vdd rc {p['r']}
C1 rc 0 {p['c']}
Bsch reset_n 0 V=V(rc)>0.7*V(vdd) ? V(vdd) : 0"""


@circuit(
    id="ring_oscillator", name="Oscilador em anel CMOS (clock de CI)", category="computador",
    summary="Número ímpar de inversores em anel: oscila com f ≈ 1/(2·N·td).",
    params=[Param("n", "Nº de inversores (ímpar)", 5, "", 3, 11), Param("vdd", "Vdd", 3.3, "V", 1.2, 5),
            Param("cl", "Carga por estágio", 100e-15, "F", 1e-15, 1e-12)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 10e-12, "stop": 40e-9 * p["cl"] / 100e-15, "maxstep": 10e-12, "uic": True}},
    probes=["n1", "n2", "n3"], sweepable=True,
    lesson=Lesson(objetivo="Ver como se gera um clock simples dentro de um circuito integrado.",
                  teoria=["Cada inversor atrasa o sinal por td. Com N ímpar o anel nunca se estabiliza e oscila a f = 1/(2·N·td).",
                          "O mesmo princípio mede velocidade de processo em fábricas de chips."],
                  observe=["Cada nó é uma onda quadrada defasada da anterior."],
                  experimentos=["Troque 5 por 9 inversores e compare as frequências.", "Aumente a carga: oscila mais lento."]))
def ring(p):
    n = int(round(p["n"]))
    n = n if n % 2 == 1 else n + 1
    lines = [f"Vdd vdd 0 DC {p['vdd']}"]
    for i in range(1, n + 1):
        a, b = f"n{i}", f"n{i % n + 1}"
        lines += [f"MP{i} {b} {a} vdd vdd PMLOG W=40u L=1u", f"MN{i} {b} {a} 0 0 NMLOG W=10u L=1u",
                  f"Cl{i} {b} 0 {p['cl']}"]
    lines.append(".ic v(n1)=0 v(n2)=" + f"{p['vdd']}")
    return "\n".join(lines)
