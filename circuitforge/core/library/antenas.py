"""Antenas e RF: dipolo equivalente, transformador λ/4, casador L, filtro de antena e balun de TV."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit

GAMMA = "Bg gamma 0 V=2*V(ant)-V(src)"   # |Γ| = |(Zin−Z0)/(Zin+Z0)| quando a fonte tem Z0 em série e Vs = 1 V


@circuit(
    id="dipole_equivalent", name="Dipolo de meia-onda – circuito equivalente RLC", category="antenas",
    summary="A antena vista como impedância: 73 Ω de radiação em série com reatâncias que se anulam em f0.",
    params=[Param("f0", "Frequência de ressonância", 146e6, "Hz", 1e6, 1e9), Param("rrad", "Resistência de radiação", 73.0, "Ω", 5, 300),
            Param("q", "Fator de qualidade", 8.0, "", 1, 50), Param("z0", "Linha de transmissão", 50.0, "Ω", 25, 300)],
    analyses=lambda p: {"Casamento (AC)": ac(p["f0"] * 0.5, p["f0"] * 1.5, 200)}, probes=["gamma", "ant"],
    theory=lambda p: {"Coeficiente de reflexão em f0 |Γ|": (abs((p["rrad"] + 1 - p["z0"]) / (p["rrad"] + 1 + p["z0"])), ""),
                      "ROE (VSWR) em f0": ((1 + abs((p["rrad"] + 1 - p["z0"]) / (p["rrad"] + 1 + p["z0"]))) /
                                           (1 - abs((p["rrad"] + 1 - p["z0"]) / (p["rrad"] + 1 + p["z0"]))), ""),
                      "Comprimento de onda λ": (3e8 / p["f0"], "m"), "Comprimento do dipolo ≈ 0,47 λ": (0.47 * 3e8 / p["f0"], "m")},
    lesson=Lesson(objetivo="Modelar uma antena como carga elétrica e medir o casamento (ROE/VSWR).",
                  teoria=["Na ressonância a reatância é zero e a antena é puramente resistiva (≈ 73 Ω, que é a resistência de radiação).",
                          "Γ = (Zin − Z0)/(Zin + Z0); ROE = (1+|Γ|)/(1−|Γ|). Quanto menor o |Γ| mais potência é irradiada.",
                          "Q alto = antena de banda estreita."],
                  observe=["O vale da curva |Γ| ocorre em f0. Veja o gráfico de ROE na aba Instrumentos."],
                  experimentos=["Reduza Q e veja a largura de banda aumentar.", "Altere a resistência de radiação para 36 Ω (monopolo)."]))
def dipole(p):
    w0 = 2 * PI * p["f0"]
    L = p["q"] * (p["rrad"] + 1) / w0
    C = 1 / (w0 ** 2 * L)
    return f"""Vs src 0 AC 1
Rs src ant {p['z0']}
Rrad ant a1 {p['rrad']}
Rloss a1 a2 1
Ld a2 a3 {L:.6g}
Cd a3 0 {C:.6g}
{GAMMA}"""


@circuit(
    id="quarter_wave_transformer", name="Transformador de impedância λ/4 (linha de transmissão)", category="antenas",
    summary="Um segmento de linha com λ/4 e Z = √(Zs·ZL) casa uma carga à linha.",
    params=[Param("f0", "Frequência central", 100e6, "Hz", 1e6, 1e9), Param("zs", "Impedância da linha de alimentação", 50.0, "Ω", 10, 300),
            Param("zl", "Impedância da antena/carga", 200.0, "Ω", 10, 1000), Param("z0", "Z do segmento (0 = automático)", 0.0, "Ω", 0, 500)],
    analyses=lambda p: {"Casamento (AC)": ac(p["f0"] * 0.2, p["f0"] * 1.8, 200)}, probes=["gamma"],
    theory=lambda p: {"Z do segmento λ/4 = √(Zs·ZL)": (math.sqrt(p["zs"] * p["zl"]), "Ω"),
                      "Comprimento λ/4 (no vácuo)": (3e8 / p["f0"] / 4, "m"),
                      "Comprimento com fator de velocidade 0,66": (0.66 * 3e8 / p["f0"] / 4, "m")},
    lesson=Lesson(objetivo="Casar impedâncias com um pedaço de cabo.",
                  teoria=["Uma linha de λ/4 inverte a impedância: Zin = Z0²/ZL. Escolhendo Z0 = √(Zs·ZL) → Zin = Zs, casamento perfeito.",
                          "Funciona numa faixa em torno de f0 (banda estreita); repete em 3·f0, 5·f0..."],
                  observe=["Γ ≈ 0 em f0 e em 3·f0."],
                  experimentos=["Mude Z do segmento manualmente (ex.: 50 Ω) e compare com o casamento perfeito."]))
def qw(p):
    z0 = p["z0"] if p["z0"] > 0 else math.sqrt(p["zs"] * p["zl"])
    return f"""Vs src 0 AC 1
Rs src ant {p['zs']}
T1 ant 0 load 0 Z0={z0:.6g} F={p['f0']:.6g} NL=0.25
Rl load 0 {p['zl']}
Bg gamma 0 V=2*V(ant)-V(src)"""


def _lmatch(p):
    q = math.sqrt(p["rs"] / p["rl"] - 1)
    w = 2 * PI * p["f0"]
    xc = p["rs"] / q
    xl = q * p["rl"]
    return q, 1 / (w * xc), xl / w


@circuit(
    id="l_match", name="Rede de casamento em L (50 Ω → carga menor)", category="antenas",
    summary="Capacitor em paralelo + indutor em série transformam a impedância de uma antena curta para 50 Ω.",
    params=[Param("f0", "Frequência", 14.2e6, "Hz", 1e6, 500e6), Param("rs", "Impedância da fonte", 50.0, "Ω", 20, 300),
            Param("rl", "Impedância da antena", 12.5, "Ω", 2, 49)],
    analyses=lambda p: {"Casamento (AC)": ac(p["f0"] * 0.5, p["f0"] * 1.5, 150)}, probes=["gamma"],
    theory=lambda p: {"Q da rede": (_lmatch(p)[0], ""), "C (paralelo, lado da fonte)": (_lmatch(p)[1], "F"), "L (série, lado da carga)": (_lmatch(p)[2], "H")},
    lesson=Lesson(objetivo="Projetar o 'acoplador de antena' (antenna tuner).",
                  teoria=["Para casar Rs > RL: Q = √(Rs/RL − 1); Xshunt = Rs/Q; Xserie = Q·RL. Usa-se C em paralelo e L em série (passa-baixa)."],
                  observe=["Γ cai a zero em f0; a largura de banda diminui com Q."],
                  experimentos=["RL = 5 Ω aumenta Q e estreita a banda."]))
def lmatch(p):
    _, C, L = _lmatch(p)
    return f"""Vs src 0 AC 1
Rs src ant {p['rs']}
Cm ant 0 {C:.6g}
Lm ant load {L:.6g}
Rl load 0 {p['rl']}
Bg gamma 0 V=2*V(ant)-V(src)"""


def _bp(p):
    r, w0, b = 50.0, 2 * PI * p["f0"], 2 * PI * p["bw"]
    g1, g2 = 1.0, 2.0
    return {"Cp": g1 / (r * b), "Lp": r * b / (g1 * w0 ** 2), "Ls": g2 * r / b, "Cs": b / (g2 * r * w0 ** 2)}


@circuit(
    id="antenna_bandpass", name="Filtro passa-faixa de antena (Butterworth de 3ª ordem)", category="antenas",
    summary="Seleciona a faixa de FM (88–108 MHz) e rejeita sinais fora dela.",
    params=[Param("f0", "Frequência central", 98e6, "Hz", 1e6, 1e9), Param("bw", "Largura de banda (−3 dB)", 20e6, "Hz", 1e5, 5e8)],
    analyses=lambda p: {"AC (Bode)": ac(p["f0"] * 0.2, p["f0"] * 3, 100)}, probes=["out"],
    theory=lambda p: {**{k: (v, "H" if k[0] == "L" else "F") for k, v in _bp(p).items()}, "Q do filtro f0/BW": (p["f0"] / p["bw"], "")},
    lesson=Lesson(objetivo="Evitar que sinais fortes de outras faixas saturem o receptor (seletividade de entrada).",
                  teoria=["Protótipo passa-baixa Butterworth (g = 1, 2, 1) é transformado em passa-faixa: ramos paralelos LC em derivação e um série LC.",
                          "Atenuação no meio da faixa ≈ 6 dB (casada nos dois lados: 50 Ω/50 Ω)."],
                  observe=["−3 dB (relativo ao pico) nas bordas da faixa."],
                  experimentos=["Estreite a banda para 5 MHz e veja a rejeição de canais adjacentes aumentar."]))
def bpf(p):
    v = _bp(p)
    return f"""Vs src 0 AC 1
Rs src ant 50
Cp1 ant 0 {v['Cp']:.6g}
Lp1 ant 0 {v['Lp']:.6g}
Ls2 ant m {v['Ls']:.6g}
Cs2 m n {v['Cs']:.6g}
Cp3 n 0 {v['Cp']:.6g}
Lp3 n 0 {v['Lp']:.6g}
Rl n 0 50
Eout out 0 n 0 1
Rout out 0 1e9
Bg gamma 0 V=2*V(ant)-V(src)"""


@circuit(
    id="tv_balun_4to1", name="Balun 4:1 de antena de TV (300 Ω → 75 Ω)", category="antenas",
    summary="Transformador de banda larga casa a fita paralela de 300 Ω ao cabo coaxial de 75 Ω.",
    params=[Param("zc", "Cabo coaxial", 75.0, "Ω", 25, 150), Param("flow", "Frequência mais baixa", 54e6, "Hz", 1e6, 200e6),
            Param("k", "Acoplamento k", 0.99, "", 0.5, 0.9999)],
    analyses=lambda p: {"Casamento (AC)": ac(1e6, 1e9, 60)}, probes=["gamma"],
    theory=lambda p: {"Razão de impedâncias": (4.0, ""), "Impedância do lado de alta": (4 * p["zc"], "Ω"),
                      "L primário (Xl = 5·Z na f. baixa)": (5 * p["zc"] / (2 * PI * p["flow"]), "H")},
    lesson=Lesson(objetivo="Entender transformadores de impedância de banda larga.",
                  teoria=["Relação de impedâncias = (N2/N1)². Com N2 = 2·N1 temos 4:1: 75 Ω ↔ 300 Ω.",
                          "A indutância do primário limita a banda em baixas frequências; a indutância de dispersão (1−k) limita em altas."],
                  observe=["Γ baixo numa grande faixa (VHF) e crescente em baixas e altas frequências."],
                  experimentos=["Reduza k para 0,9 e veja a banda alta encolher."]))
def balun(p):
    l1 = 5 * p["zc"] / (2 * PI * p["flow"])
    return f"""Vs src 0 AC 1
Rs src ant {p['zc']}
L1 ant 0 {l1:.6g}
L2 sec 0 {4*l1:.6g}
K1 L1 L2 {p['k']}
Rl sec 0 {4*p['zc']}
Bg gamma 0 V=2*V(ant)-V(src)"""
