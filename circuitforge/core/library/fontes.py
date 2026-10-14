"""Fontes de alimentação: reguladores lineares, chaveados e retificadores."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, dc, OP, tran, tran_time


# ---------------------------------------------------------------------------
# Blocos reutilizados por outras categorias
# ---------------------------------------------------------------------------

def buck_netlist(vin, vout, f, L, C, esr, rload, phases=1, i_step=None, t_step=None, vdrop=0.0, sync=False):
    """Conversor buck síncrono-ideal (chave + diodo Schottky) com N fases entrelaçadas."""
    d = min(max((vout + vdrop) / vin, 0.01), 0.95)
    T = 1.0 / f
    ton = d * T
    iout = vout / rload if i_step is None else i_step[0]
    lines = [f"Vin vin 0 DC {vin}"]
    for k in range(phases):
        delay = k * T / phases
        lines += [
            f"Vg{k} g{k} 0 PULSE(0 5 {delay:.6e} 2n 2n {ton:.6e} {T:.6e})",
            f"S{k} vin sw{k} g{k} 0 {'SWPWR' if sync else 'SWM'}",
            f"D{k} 0 sw{k} DSCH",
        ]
        if sync:  # retificação síncrona: chave do lado baixo complementar com tempo morto
            td = max(delay - 10e-9, 0.0)
            lines += [f"Vgl{k} gl{k} 0 PULSE(5 0 {td:.6e} 2n 2n {ton + 20e-9:.6e} {T:.6e})",
                      f"SL{k} sw{k} 0 gl{k} 0 SWPWR"]
        lines += [
            f"L{k} sw{k} lx{k} {L} IC={iout/phases:.6g}",
            f"RL{k} lx{k} out {0.001 if sync else 0.005}",
        ]
    lines += [f"C1 out cx {C} IC={vout}", f"Resr cx 0 {esr}"]
    if i_step is None:
        lines.append(f"Rload out 0 {rload}")
    else:
        i1, i2 = i_step
        lines.append(f"Iload out 0 PULSE({i1} {i2} {t_step:.6e} 100n 100n 1 2)")
    return "\n".join(lines)


def ldo_netlist(vin, vout, i1, i2, cout, t_step):
    """LDO com transistor PMOS de passagem e amp-op de erro (referência 1,25 V)."""
    vref = 1.25
    r2 = 10e3
    r1 = r2 * (vout / vref - 1)
    return f"""Vin vin 0 DC {vin}
Vref ref 0 DC {vref}
XU1 fb ref drv vin 0 OPAMP
M1 out drv vin vin PMOSP W=1 L=1
R1 out fb {r1:.6g}
R2 fb 0 {r2:.6g}
C1 out cx {cout} IC={vout}
Resr cx 0 0.2
Rpre out 0 {vout/0.01:.6g}
Iload out 0 PULSE({i1} {i2} {t_step:.6e} 1u 1u 1 2)"""


# ---------------------------------------------------------------------------

@circuit(
    id="zener_regulator", name="Regulador shunt com diodo Zener", category="fontes",
    summary="O Zener mantém a tensão quase constante enquanto houver corrente reversa suficiente.",
    params=[Param("vz", "Tensão Zener", 5.1, "V", 2.4, 30), Param("rs", "Resistor série", 220.0, "Ω", 10, 1e5),
            Param("rl", "Carga", 1e3, "Ω", 50, 1e6), Param("vin", "Tensão de entrada", 12.0, "V", 3, 60)],
    analyses=lambda p: {"Regulação de linha (DC)": dc("Vin", 0, 2 * p["vin"], p["vin"] / 40), "Ponto de operação": OP},
    probes=["out"],
    theory=lambda p: {"Corrente no resistor": ((p["vin"] - p["vz"]) / p["rs"], "A"),
                      "Corrente na carga": (p["vz"] / p["rl"], "A"),
                      "Corrente no Zener": ((p["vin"] - p["vz"]) / p["rs"] - p["vz"] / p["rl"], "A"),
                      "Potência no Zener": (p["vz"] * max((p["vin"] - p["vz"]) / p["rs"] - p["vz"] / p["rl"], 0), "W")},
    lesson=Lesson(objetivo="Entender a regulação mais simples de todas.",
                  teoria=["Acima de Vz o diodo conduz e fixa a tensão; Rs absorve a diferença.",
                          "Se a carga puxar mais corrente que (Vin−Vz)/Rs, o Zener desliga e a regulação se perde."],
                  observe=["Na curva DC, a saída acompanha a entrada até Vz e depois achata."],
                  experimentos=["Diminua RL até a saída cair (Zener sem corrente)."],
                  cuidados=["Dissipe a potência do Zener e de Rs."]))
def zener_regulator(p):
    return f""".model DZ D(Is=1e-14 Bv={p['vz']} Ibv=5m Rs=2 N=1)
Vin vin 0 DC {p['vin']}
Rs vin out {p['rs']}
D1 0 out DZ
Rl out 0 {p['rl']}"""


@circuit(
    id="series_regulator", name="Regulador série (Zener + transistor)", category="fontes",
    summary="Seguidor de emissor com referência Zener: o transistor amplifica a corrente da carga.",
    params=[Param("vz", "Tensão Zener", 6.8, "V", 3.3, 30), Param("vin", "Tensão de entrada", 15.0, "V", 5, 60),
            Param("rl", "Carga", 50.0, "Ω", 2, 1e5)],
    analyses=lambda p: {"Regulação de linha (DC)": dc("Vin", 0, 1.5 * p["vin"], p["vin"] / 40), "Ponto de operação": OP},
    probes=["out", "b"],
    theory=lambda p: {"Vout ≈ Vz − VBE": (p["vz"] - 0.7, "V"), "Corrente de carga": ((p["vz"] - 0.7) / p["rl"], "A"),
                      "Dissipação no transistor": ((p["vin"] - p["vz"] + 0.7) * (p["vz"] - 0.7) / p["rl"], "W")},
    lesson=Lesson(objetivo="Ver como estender o Zener a correntes maiores.",
                  teoria=["O ganho β do transistor reduz a corrente exigida do Zener por β.",
                          "A regulação é ruim para grandes variações de carga: a solução é realimentação (próximo circuito)."],
                  observe=["A saída fica ~0,7 V abaixo do Zener."],
                  experimentos=["Reduza RL a 10 Ω e observe a potência no transistor."]))
def series_regulator(p):
    return f""".model DZ D(Is=1e-14 Bv={p['vz']} Ibv=5m Rs=2 N=1)
Vin vin 0 DC {p['vin']}
Rz vin b 1k
D1 0 b DZ
Q1 vin b out QPOWN
Rl out 0 {p['rl']}"""


@circuit(
    id="ldo_adjustable", name="Regulador linear ajustável com amp-op (LDO com PMOS)", category="fontes",
    summary="Amp-op compara a saída (divisor) com a referência de 1,25 V e comanda o PMOS de passagem.",
    params=[Param("vin", "Tensão de entrada", 9.0, "V", 4, 40), Param("vout", "Tensão de saída", 5.0, "V", 2, 30),
            Param("i1", "Corrente de carga inicial", 0.05, "A", 0.001, 1), Param("i2", "Corrente após degrau", 0.4, "A", 0.001, 1),
            Param("cout", "Capacitor de saída", 22e-6, "F", 1e-7, 1e-2)],
    analyses=lambda p: {"Degrau de carga": tran_time(400e-6, 4000)},
    probes=["out"],
    theory=lambda p: {"Vout = Vref(1+R1/R2)": (p["vout"], "V"),
                      "Dissipação no transistor (carga final)": ((p["vin"] - p["vout"]) * p["i2"], "W"),
                      "Rendimento (carga final)": (p["vout"] / p["vin"], "")},
    lesson=Lesson(objetivo="Entender regulação por realimentação e o limite de eficiência de um regulador linear.",
                  teoria=["O amp-op força V(fb) = 1,25 V; logo Vout = 1,25·(1 + R1/R2).",
                          "Eficiência = Vout/Vin: toda a diferença vira calor no transistor."],
                  observe=["No degrau de carga a saída sofre um pequeno afundamento e recupera."],
                  experimentos=["Reduza Cout e veja o afundamento aumentar."],
                  cuidados=["Mantenha Vin ≥ Vout + 1 V (queda do PMOS) – o amp-op satura 1 V abaixo do trilho."]))
def ldo(p):
    return ldo_netlist(p["vin"], p["vout"], p["i1"], p["i2"], p["cout"], 150e-6)


def _buck_theory(p):
    d = p["vout"] / p["vin"]
    di = (p["vin"] - p["vout"]) * d / (p["l"] * p["f"])
    iout = p["vout"] / p["rl"]
    return {"Ciclo de trabalho D = Vout/Vin": (d, ""), "Ondulação da corrente no indutor ΔIL": (di, "A"),
            "Ondulação de tensão ≈ ΔIL/(8fC)": (di / (8 * p["f"] * p["c"]) + di * p["esr"], "V"),
            "Corrente de saída": (iout, "A"),
            "Modo de condução": (1.0 if iout > di / 2 else 0.0, "1=contínuo (CCM), 0=descontínuo")}


@circuit(
    id="buck_converter", name="Conversor buck (abaixador chaveado)", category="fontes",
    summary="Chave + diodo + LC: Vout = D·Vin com rendimento alto.",
    params=[Param("vin", "Tensão de entrada", 12.0, "V", 3, 100), Param("vout", "Tensão de saída desejada", 5.0, "V", 0.5, 90),
            Param("f", "Frequência de chaveamento", 100e3, "Hz", 5e3, 2e6), Param("l", "Indutor", 47e-6, "H", 1e-7, 1e-2),
            Param("c", "Capacitor de saída", 100e-6, "F", 1e-7, 1e-2), Param("esr", "ESR do capacitor", 0.02, "Ω", 0.0005, 2),
            Param("rl", "Carga", 5.0, "Ω", 0.2, 1e4)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["f"] / 100, "stop": 150 / p["f"], "maxstep": 1 / p["f"] / 200, "uic": True}},
    probes=["out", "sw0"], theory=_buck_theory,
    lesson=Lesson(objetivo="Entender o conversor DC-DC mais comum em placas e carregadores.",
                  teoria=["Com a chave ligada a corrente do indutor sobe; desligada, o diodo mantém a corrente e ela desce.",
                          "Em regime, Vout = D·Vin. O LC filtra o chaveamento deixando uma pequena ondulação."],
                  observe=["O nó 'sw0' é uma onda quadrada entre Vin e −0,4 V; 'out' é praticamente DC."],
                  experimentos=["Aumente L para reduzir a ondulação de corrente.", "Reduza a frequência e observe a ondulação crescer.",
                                "Aumente a carga (R menor) até o conversor entrar em modo descontínuo."],
                  cuidados=["Este modelo é de malha aberta: o ciclo D é fixo. A tensão real cai um pouco com a carga."]))
def buck(p):
    return buck_netlist(p["vin"], p["vout"], p["f"], p["l"], p["c"], p["esr"], p["rl"], vdrop=0.15)


@circuit(
    id="boost_converter", name="Conversor boost (elevador chaveado)", category="fontes",
    summary="Eleva a tensão: Vout = Vin/(1−D).",
    params=[Param("vin", "Tensão de entrada", 5.0, "V", 1, 50), Param("d", "Ciclo de trabalho D", 0.5, "", 0.05, 0.85),
            Param("f", "Frequência", 100e3, "Hz", 5e3, 2e6), Param("l", "Indutor", 100e-6, "H", 1e-7, 1e-2),
            Param("c", "Capacitor de saída", 100e-6, "F", 1e-7, 1e-2), Param("rl", "Carga", 50.0, "Ω", 2, 1e4)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["f"] / 100, "stop": 400 / p["f"], "maxstep": 1 / p["f"] / 200, "uic": True}},
    probes=["out", "sw"],
    theory=lambda p: {"Vout ideal = Vin/(1−D)": (p["vin"] / (1 - p["d"]), "V"),
                      "Corrente média no indutor": (p["vin"] / (1 - p["d"]) ** 2 / p["rl"], "A"),
                      "Ondulação do indutor": (p["vin"] * p["d"] / (p["l"] * p["f"]), "A")},
    lesson=Lesson(objetivo="Entender como elevar tensão com indutor (baterias → 5 V/12 V, LEDs, painéis solares).",
                  teoria=["Com a chave fechada o indutor armazena energia; ao abrir, ela é entregue à saída somada à entrada.",
                          "A relação ideal vale em modo contínuo; perdas limitam D a ~0,8."],
                  observe=["O nó 'sw' pula acima da tensão de saída."],
                  experimentos=["D = 0,75 deve dar Vout ≈ 4·Vin (menos perdas)."],
                  cuidados=["Nunca opere em malha aberta sem carga: a tensão sobe sem limite."]))
def boost(p):
    T = 1 / p["f"]
    vout = p["vin"] / (1 - p["d"])
    iin = vout ** 2 / p["rl"] / p["vin"]
    return f"""Vin vin 0 DC {p['vin']}
L1 vin sw {p['l']} IC={iin:.6g}
Vg g 0 PULSE(0 5 0 2n 2n {p['d']*T:.6e} {T:.6e})
S1 sw 0 g 0 SWM
D1 sw out DSCH
C1 out 0 {p['c']} IC={vout:.6g}
Rload out 0 {p['rl']}"""


def _ripple_theory(p):
    vp = p["vac"] - 1.4
    iload = vp / p["rl"]
    return {"Pico retificado": (vp, "V"), "Ondulação ≈ I/(2·f·C)": (iload / (2 * p["f"] * p["c"]), "V"),
            "Corrente de carga": (iload, "A")}


@circuit(
    id="rectifier_filter", name="Retificador com filtro capacitivo", category="fontes",
    summary="Ponte + capacitor: DC com ondulação (ripple) ΔV ≈ I/(2fC).",
    params=[Param("vac", "Pico da tensão AC", 17.0, "V", 3, 400), Param("f", "Frequência da rede", 60.0, "Hz", 40, 400),
            Param("c", "Capacitor de filtro", 2200e-6, "F", 1e-6, 0.1), Param("rl", "Carga", 100.0, "Ω", 2, 1e5),
            Param("rs", "Resistência do trafo", 1.0, "Ω", 0.01, 50)],
    analyses=lambda p: {"Transient": tran(p["f"], max(10, min(3 * p["rl"] * p["c"] * p["f"], 60)), 300)},
    probes=["vl", "ac1"], theory=_ripple_theory,
    lesson=Lesson(objetivo="Dimensionar o capacitor de filtro de uma fonte.",
                  teoria=["O capacitor carrega nos picos e alimenta a carga entre eles: ΔV ≈ I/(2fC) para ponte.",
                          "Os diodos conduzem em pulsos curtos de corrente (alto fator de crista)."],
                  observe=["Veja os pulsos de corrente de recarga em i(vin)."],
                  experimentos=["Divida C por 2: a ondulação dobra."]))
def rect_filter(p):
    return f"""Vin src ac2 SIN(0 {p['vac']} {p['f']})
Rs src ac1 {p['rs']}
Rgnd ac2 0 1e9
D1 ac1 outp DSI
D2 ac2 outp DSI
D3 0 ac1 DSI
D4 0 ac2 DSI
C1 outp 0 {p['c']}
RL outp 0 {p['rl']}
Bvl vl 0 V=V(outp)"""


@circuit(
    id="linear_psu", name="Fonte linear completa (trafo + ponte + filtro + regulador)", category="fontes",
    summary="Rede → transformador → ponte → capacitor → regulador série. A fonte clássica de bancada.",
    params=[Param("vrms", "Rede (RMS)", 127.0, "V", 100, 240), Param("n", "Relação do trafo (n:1)", 8.0, "", 2, 40),
            Param("f", "Frequência", 60.0, "Hz", 40, 400), Param("c", "Capacitor", 2200e-6, "F", 1e-5, 0.1),
            Param("vz", "Zener de referência", 9.1, "V", 3.3, 30), Param("rl", "Carga", 30.0, "Ω", 3, 1e4)],
    analyses=lambda p: {"Transient": tran(p["f"], 14, 300)}, probes=["raw", "reg", "sec"],
    theory=lambda p: {"Pico no secundário": (p["vrms"] * math.sqrt(2) / p["n"], "V"),
                      "Tensão filtrada (pico − 1,4 V)": (p["vrms"] * math.sqrt(2) / p["n"] - 1.4, "V"),
                      "Saída regulada ≈ Vz − 0,7": (p["vz"] - 0.7, "V")},
    lesson=Lesson(objetivo="Visualizar cada etapa de uma fonte linear.",
                  teoria=["Transformador reduz a tensão pela relação de espiras; ponte retifica; capacitor filtra; regulador estabiliza.",
                          "A tensão não regulada (raw) precisa ficar acima de Vout + queda do regulador mesmo no vale da ondulação."],
                  observe=["Compare 'sec' (senoide), 'raw' (ondulada) e 'reg' (quase constante)."],
                  experimentos=["Aumente a carga e veja o raw cair até o regulador perder a regulação."]))
def linear_psu(p):
    lp = 5.0
    ls = lp / p["n"] ** 2
    return f""".model DZ D(Is=1e-14 Bv={p['vz']} Ibv=5m Rs=2 N=1)
Vmains m 0 SIN(0 {p['vrms']*math.sqrt(2):.6g} {p['f']})
Rp m p1 2
L1 p1 0 {lp}
L2 sec 0 {ls:.6g}
K1 L1 L2 0.999
Rw sec s1 0.2
D1 s1 raw DSI
D2 0 s1 DSI
C1 raw 0 {p['c']}
Rz raw b 1k
D3 0 b DZ
Q1 raw b reg QPOWN
Rl reg 0 {p['rl']}
Rbleed raw 0 10k"""
