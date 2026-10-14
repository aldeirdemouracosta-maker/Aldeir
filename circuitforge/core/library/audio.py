"""Amplificadores de som: pré-amp, classe AB, classe D e divisor de frequências."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, tran, tran_time


@circuit(
    id="audio_preamp", name="Pré-amplificador de áudio (amp-op, acoplamento AC)", category="audio",
    summary="Estágio não-inversor com capacitores de acoplamento e polarização central.",
    params=[Param("rf", "Rf", 47e3, "Ω", 1e3, 1e6), Param("rg", "Rg", 4.7e3, "Ω", 100, 1e5), Param("a", "Entrada (pico)", 0.05, "V", 0.001, 1),
            Param("f", "Frequência", 1e3, "Hz", 20, 2e4)],
    analyses=lambda p: {"AC (Bode)": ac(1, 1e6, 30), "Transient": tran(p["f"], 5)}, probes=["in", "out"],
    theory=lambda p: {"Ganho 1+Rf/Rg": (1 + p["rf"] / p["rg"], "V/V"), "Ganho (dB)": (20 * math.log10(1 + p["rf"] / p["rg"]), "dB"),
                      "Corte inferior (Cin, 100 kΩ)": (1 / (2 * PI * 100e3 * 1e-6), "Hz"),
                      "Corte superior ≈ GBW/ganho": (1e6 / (1 + p["rf"] / p["rg"]), "Hz")},
    lesson=Lesson(objetivo="Amplificar sinais de microfone/instrumento sem alterar o nível DC.",
                  teoria=["Cin e o resistor de 100 kΩ formam um passa-altas que bloqueia DC.", "Cg em série com Rg torna o ganho DC unitário, evitando amplificar offsets."],
                  observe=["Banda passante plana de dezenas de Hz até dezenas de kHz."],
                  experimentos=["Aumente o ganho para 100 e veja a banda cair para 10 kHz (limite do GBW)."]))
def preamp(p):
    return f"""Vcc vcc 0 DC 12
Vee vee 0 DC -12
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
Cin in inp 1u
Rb inp 0 100k
Rf out inn {p['rf']}
Rg inn g {p['rg']}
Cg g 0 100u
XU1 inp inn out vcc vee OPAMP
Rl out 0 10k"""


@circuit(
    id="class_ab_amp", name="Amplificador de potência classe AB (amp-op + par complementar)", category="audio",
    summary="Par NPN/PNP polarizado por diodos dentro da malha de realimentação do amp-op.",
    params=[Param("vcc", "Alimentação ±", 15.0, "V", 6, 50), Param("rg", "Rg", 1e3, "Ω", 100, 1e5), Param("rf", "Rf", 10e3, "Ω", 1e3, 1e6),
            Param("a", "Entrada (pico)", 0.5, "V", 0.01, 5), Param("rl", "Alto-falante", 8.0, "Ω", 2, 100),
            Param("bias", "Polarização (0 = classe B, 1 = classe AB)", 1, "", 0, 1), Param("f", "Frequência", 1e3, "Hz", 20, 2e4)],
    analyses=lambda p: {"Transient": tran(p["f"], 6, 300), "AC (Bode)": ac(10, 1e6, 30)}, probes=["in", "out"],
    theory=lambda p: {"Ganho 1+Rf/Rg": (1 + p["rf"] / p["rg"], "V/V"),
                      "Potência máxima ≈ (Vcc−2)²/(2RL)": ((p["vcc"] - 2) ** 2 / (2 * p["rl"]), "W"),
                      "Corrente de pico na carga": ((p["vcc"] - 2) / p["rl"], "A")},
    lesson=Lesson(objetivo="Entender classes de operação e distorção de crossover.",
                  teoria=["Classe B: cada transistor conduz meio ciclo; a zona morta de ±0,65 V causa distorção de crossover.",
                          "Classe AB: diodos polarizam levemente os dois transistores e eliminam a zona morta.",
                          "A realimentação do amp-op reduz distorção, mas não a elimina em classe B."],
                  observe=["Use o osciloscópio e o analisador de THD com bias = 0 e bias = 1."],
                  experimentos=["Reduza a amplitude de entrada: em classe B a distorção relativa aumenta."],
                  cuidados=["Em hardware real use resistores de emissor e dissipador; cuidado com fuga térmica."]))
def class_ab(p):
    rb = max(150.0, (p["vcc"] * 2 - 1.3) / 0.08)
    bias = "D1 bn drv DBIAS\nD2 drv bp DBIAS" if p["bias"] >= 0.5 else "Rb1 bn drv 0.01\nRb2 drv bp 0.01"
    return f"""Vcc vcc 0 DC {p['vcc']}
Vee vee 0 DC -{p['vcc']}
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
XU1 in fb drv vcc vee OPAMP
Rf out fb {p['rf']}
Rg fb 0 {p['rg']}
.model QAUN NPN(Is=1e-13 Bf=300 Vaf=100 Rb=0.5 Re=0.05 Cje=100p Cjc=50p)
.model QAUP PNP(Is=1e-13 Bf=300 Vaf=100 Rb=0.5 Re=0.05 Cje=100p Cjc=50p)
.model DBIAS D(Is=3e-13 N=1 Rs=0.5)
Rbn vcc bn {rb:.6g}
{bias}
Rbp bp vee {rb:.6g}
Q1 vcc bn e1 QAUN
Q2 vee bp e2 QAUP
Re1 e1 out 0.22
Re2 e2 out 0.22
RL out 0 {p['rl']}"""


@circuit(
    id="class_d_amp", name="Amplificador classe D (PWM + filtro LC)", category="audio",
    summary="Comparador gera PWM, meia-ponte chaveia e o filtro LC recupera o áudio com alta eficiência.",
    params=[Param("vs", "Alimentação ±", 20.0, "V", 5, 60), Param("a", "Áudio (pico, fração da portadora)", 0.6, "", 0.05, 0.95),
            Param("fa", "Frequência do áudio", 1e3, "Hz", 100, 8e3), Param("fc", "Portadora PWM", 150e3, "Hz", 50e3, 500e3),
            Param("l", "Indutor de saída", 22e-6, "H", 1e-6, 1e-3), Param("c", "Capacitor de saída", 0.47e-6, "F", 1e-8, 1e-5),
            Param("rl", "Alto-falante", 8.0, "Ω", 2, 100)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["fc"] / 60, "stop": 3 / p["fa"], "maxstep": 1 / p["fc"] / 60}},
    probes=["in", "sw", "out"],
    theory=lambda p: {"Pico de saída ≈ a·Vs": (p["a"] * p["vs"], "V"), "Corte do filtro LC": (1 / (2 * PI * math.sqrt(p["l"] * p["c"])), "Hz"),
                      "Potência na carga": ((p["a"] * p["vs"]) ** 2 / (2 * p["rl"]), "W")},
    lesson=Lesson(objetivo="Compreender a eficiência dos amplificadores de áudio modernos.",
                  teoria=["A razão cíclica do PWM é proporcional ao sinal de áudio; o filtro LC elimina a portadora.",
                          "Como os transistores só estão ligados ou desligados, quase não dissipam: eficiência > 90 %."],
                  observe=["'sw' é PWM entre ±Vs; 'out' é a senoide filtrada."],
                  experimentos=["Reduza a portadora e veja a ondulação residual aumentar."]))
def class_d(p):
    T = 1 / p["fc"]
    return f"""Vp vp 0 DC {p['vs']}
Vn vn 0 DC -{p['vs']}
Vin in 0 SIN(0 {p['a']} {p['fa']})
Vtri tri 0 PULSE(-1 1 0 {T/2 - 1e-9:.6e} {T/2 - 1e-9:.6e} 2n {T:.6e})
Bgh gh 0 V=V(in)>V(tri) ? 1 : 0
Bgl gl 0 V=V(in)>V(tri) ? 0 : 1
S1 vp sw gh 0 SWPWR
S2 sw vn gl 0 SWPWR
L1 sw lo {p['l']}
C1 lo out {p['c']}
Cx out 0 1n
RL out 0 {p['rl']}
Rcap lo 0 1e6"""


def _xo(p):
    L = p["r"] * math.sqrt(2) / (2 * PI * p["fc"])
    C = 1 / (2 * PI * p["fc"] * p["r"] * math.sqrt(2))
    return L, C


@circuit(
    id="crossover_2way", name="Divisor de frequências (crossover) de 2 vias", category="audio",
    summary="Filtro passivo de 2ª ordem (Butterworth) divide graves para o woofer e agudos para o tweeter.",
    params=[Param("fc", "Frequência de cruzamento", 2500.0, "Hz", 200, 10000), Param("r", "Impedância dos alto-falantes", 8.0, "Ω", 2, 16)],
    analyses=lambda p: {"AC (Bode)": ac(20, 40e3, 40)}, probes=["woofer", "tweeter"],
    theory=lambda p: {"L (série woofer / paralelo tweeter)": (_xo(p)[0], "H"), "C (paralelo woofer / série tweeter)": (_xo(p)[1], "F"),
                      "Atenuação em fc": (-3.01, "dB")},
    lesson=Lesson(objetivo="Projetar a caixa acústica de 2 vias.",
                  teoria=["Woofer: indutor em série (bloqueia agudos) + capacitor em paralelo. Tweeter: capacitor em série (bloqueia graves) + indutor em paralelo.",
                          "L = R√2/(2πfc) e C = 1/(2πfc R√2) para Butterworth de 2ª ordem; 12 dB/oitava."],
                  observe=["As duas curvas se cruzam em −3 dB na frequência de cruzamento."],
                  experimentos=["Mude fc para 1,5 kHz e note os novos valores de L e C."],
                  cuidados=["Alto-falantes reais têm impedância variável com a frequência; use Zobel para corrigir."]))
def crossover(p):
    L, C = _xo(p)
    return f"""Vin in 0 AC 1
Rs in s 0.05
Lw s woofer {L:.6g}
Cw woofer 0 {C:.6g}
Rw woofer 0 {p['r']}
Ct s tweeter {C:.6g}
Lt tweeter 0 {L:.6g}
Rt tweeter 0 {p['r']}"""
