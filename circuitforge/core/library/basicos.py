"""Fundamentos: filtros RC, divisor, RLC, retificadores, amp-op, BJT e 555."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, dc, OP, tran, tran_time

SIN = "SIN(0 {a} {f}) AC 1"


@circuit(
    id="rc_lowpass", name="Filtro RC passa-baixa", category="basicos",
    summary="Atenua frequências acima da frequência de corte fc = 1/(2πRC).",
    params=[Param("r", "Resistência R", 1e3, "Ω", 1, 1e7), Param("c", "Capacitância C", 100e-9, "F", 1e-12, 1e-3),
            Param("a", "Amplitude de entrada", 1.0, "V", 0.001, 100), Param("f", "Frequência de entrada", 1e3, "Hz", 1, 1e7)],
    analyses=lambda p: {"Transient": tran(p["f"], 5), "AC (Bode)": ac(1, 1e6)},
    probes=["in", "out"],
    theory=lambda p: {"Frequência de corte fc": (1 / (2 * PI * p["r"] * p["c"]), "Hz"),
                      "Constante de tempo τ": (p["r"] * p["c"], "s")},
    lesson=Lesson(
        objetivo="Entender como um resistor e um capacitor formam um filtro que deixa passar graves e corta agudos.",
        teoria=["O capacitor oferece reatância Xc = 1/(2πfC): alta em baixas frequências, baixa em altas.",
                "O divisor R–Xc entrega na saída Vout/Vin = 1/√(1+(f/fc)²). Em fc o ganho é −3 dB e a fase −45°."],
        observe=["Na aba AC, veja a queda de 20 dB por década acima de fc.", "No transiente, a saída fica atrasada e menor que a entrada."],
        experimentos=["Dobre C: fc cai pela metade.", "Ajuste a frequência de entrada para fc e meça a atenuação (≈0,707)."],
    ))
def rc_lowpass(p):
    return f"""Vin in 0 {SIN.format(a=p['a'], f=p['f'])}
R1 in out {p['r']}
C1 out 0 {p['c']}"""


@circuit(
    id="rc_highpass", name="Filtro RC passa-alta", category="basicos",
    summary="Bloqueia o nível DC e frequências baixas; fc = 1/(2πRC).",
    params=[Param("r", "Resistência R", 1e3, "Ω", 1, 1e7), Param("c", "Capacitância C", 100e-9, "F", 1e-12, 1e-3),
            Param("a", "Amplitude de entrada", 1.0, "V", 0.001, 100), Param("f", "Frequência de entrada", 1e3, "Hz", 1, 1e7)],
    analyses=lambda p: {"Transient": tran(p["f"], 5), "AC (Bode)": ac(1, 1e6)},
    probes=["in", "out"],
    theory=lambda p: {"Frequência de corte fc": (1 / (2 * PI * p["r"] * p["c"]), "Hz")},
    lesson=Lesson(
        objetivo="Ver o capacitor de acoplamento como filtro passa-alta.",
        teoria=["Em baixa frequência o capacitor é quase um circuito aberto e a saída cai a zero.",
                "Este é o mesmo arranjo dos capacitores de acoplamento em amplificadores."],
        observe=["Fase positiva (+90° em baixas frequências) no Bode."],
        experimentos=["Aumente R: o corte sobe ou desce? (desce)."],
    ))
def rc_highpass(p):
    return f"""Vin in 0 {SIN.format(a=p['a'], f=p['f'])}
C1 in out {p['c']}
R1 out 0 {p['r']}"""


@circuit(
    id="rc_integrator", name="Integrador RC (onda quadrada → triangular)", category="basicos",
    summary="Com τ ≫ T o capacitor integra a entrada: quadrada vira triangular.",
    params=[Param("r", "Resistência R", 10e3, "Ω", 1, 1e7), Param("c", "Capacitância C", 100e-9, "F", 1e-12, 1e-3),
            Param("a", "Amplitude", 1.0, "V", 0.01, 50), Param("f", "Frequência", 1e3, "Hz", 1, 1e6)],
    analyses=lambda p: {"Transient": tran(p["f"], 8)}, probes=["in", "out"],
    theory=lambda p: {"τ = RC": (p["r"] * p["c"], "s"), "Período T": (1 / p["f"], "s"),
                      "Razão τ/T (integrador se ≫ 1)": (p["r"] * p["c"] * p["f"], "")},
    lesson=Lesson(
        objetivo="Mostrar integração com filtro passivo.",
        teoria=["Vout ≈ (1/RC)∫Vin dt quando a constante de tempo é muito maior que o período."],
        observe=["A saída é uma rampa subindo e descendo (triangular)."],
        experimentos=["Reduza C até τ ≈ T/10 e veja a forma voltar a ser quadrada arredondada."],
    ))
def rc_integrator(p):
    T = 1 / p["f"]
    return f"""Vin in 0 PULSE(-{p['a']} {p['a']} 0 {T/1000:.3e} {T/1000:.3e} {T/2:.6e} {T:.6e})
R1 in out {p['r']}
C1 out 0 {p['c']}"""


@circuit(
    id="rc_differentiator", name="Diferenciador RC (quadrada → pulsos)", category="basicos",
    summary="Com τ ≪ T a saída é a derivada da entrada: picos nas bordas.",
    params=[Param("r", "Resistência R", 1e3, "Ω", 1, 1e7), Param("c", "Capacitância C", 10e-9, "F", 1e-12, 1e-3),
            Param("a", "Amplitude", 1.0, "V", 0.01, 50), Param("f", "Frequência", 1e3, "Hz", 1, 1e6)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["f"] / 2000, "stop": 4 / p["f"], "maxstep": 1 / p["f"] / 2000}},
    probes=["in", "out"],
    theory=lambda p: {"τ = RC": (p["r"] * p["c"], "s"), "Período T": (1 / p["f"], "s")},
    lesson=Lesson(objetivo="Detectar bordas de sinal.",
                  teoria=["Corrente do capacitor i = C·dv/dt: só circula nas transições."],
                  observe=["Picos positivos na subida e negativos na descida, decaindo com τ."],
                  experimentos=["Aumente R e veja os pulsos ficarem mais largos."]))
def rc_differentiator(p):
    T = 1 / p["f"]
    return f"""Vin in 0 PULSE(-{p['a']} {p['a']} 0 {T/1000:.3e} {T/1000:.3e} {T/2:.6e} {T:.6e})
C1 in out {p['c']}
R1 out 0 {p['r']}"""


@circuit(
    id="voltage_divider", name="Divisor de tensão", category="basicos",
    summary="Vout = Vin·R2/(R1+R2).",
    params=[Param("r1", "R1", 10e3, "Ω", 1, 1e8), Param("r2", "R2", 10e3, "Ω", 1, 1e8), Param("vin", "Tensão de entrada", 5.0, "V", 0.1, 400)],
    analyses=lambda p: {"Ponto de operação": OP, "Varredura DC": dc("Vin", 0, p["vin"], p["vin"] / 50)},
    probes=["in", "out"],
    theory=lambda p: {"Vout": (p["vin"] * p["r2"] / (p["r1"] + p["r2"]), "V"),
                      "Corrente": (p["vin"] / (p["r1"] + p["r2"]), "A"),
                      "Potência total": (p["vin"] ** 2 / (p["r1"] + p["r2"]), "W")},
    lesson=Lesson(objetivo="Dominar o circuito mais usado da eletrônica.",
                  teoria=["A mesma corrente atravessa R1 e R2; a tensão se divide proporcionalmente às resistências.",
                          "Ligar uma carga em paralelo com R2 muda a razão (efeito de carga)."],
                  observe=["Na varredura DC a saída é uma reta de inclinação R2/(R1+R2)."],
                  experimentos=["Coloque R2 = 3·R1 e confira Vout = 75 % de Vin."]))
def voltage_divider(p):
    return f"""Vin in 0 DC {p['vin']}
R1 in out {p['r1']}
R2 out 0 {p['r2']}"""


@circuit(
    id="series_rlc", name="Circuito RLC série (ressonância)", category="basicos",
    summary="Ressonância em f0 = 1/(2π√LC); a tensão no capacitor sobe por Q.",
    params=[Param("r", "R", 50.0, "Ω", 0.1, 1e5), Param("l", "L", 10e-3, "H", 1e-9, 10), Param("c", "C", 100e-9, "F", 1e-12, 1e-3),
            Param("a", "Amplitude", 1.0, "V", 0.01, 50)],
    analyses=lambda p: {"AC (Bode)": ac(p0(p) / 100, p0(p) * 100, 40), "Transient": tran_time(10 / p0(p), 2000)},
    probes=["in", "out"],
    theory=lambda p: {"Frequência de ressonância f0": (p0(p), "Hz"),
                      "Fator de qualidade Q": (math.sqrt(p["l"] / p["c"]) / p["r"], ""),
                      "Largura de banda": (p0(p) / (math.sqrt(p["l"] / p["c"]) / p["r"]), "Hz")},
    lesson=Lesson(objetivo="Entender ressonância, base de sintonizadores e filtros de rádio.",
                  teoria=["Em f0 as reatâncias XL e Xc se cancelam e só R limita a corrente.",
                          "Q = √(L/C)/R mede a seletividade: Q alto = pico estreito."],
                  observe=["No Bode, o pico de out sobre Vin vale ≈ Q na ressonância."],
                  experimentos=["Reduza R para 10 Ω e veja Q subir cinco vezes."]))
def series_rlc(p):
    return f"""Vin in 0 SIN(0 {p['a']} {p0(p)}) AC 1
R1 in mid {p['r']}
L1 mid out {p['l']}
C1 out 0 {p['c']}"""


def p0(p):
    return 1 / (2 * PI * math.sqrt(p["l"] * p["c"]))


def _rect_an(p):
    return {"Transient": tran(p["f"], 4, 400)}


@circuit(
    id="halfwave_rectifier", name="Retificador de meia-onda", category="basicos",
    summary="Um diodo conduz só os semiciclos positivos.",
    params=[Param("r", "Carga", 1e3, "Ω", 1, 1e6), Param("a", "Amplitude de pico", 10.0, "V", 1, 400), Param("f", "Frequência", 60.0, "Hz", 1, 1e5)],
    analyses=_rect_an, probes=["in", "out"],
    theory=lambda p: {"Pico na carga (−0,7 V)": (p["a"] - 0.7, "V"), "Valor médio ≈ Vp/π": ((p["a"] - 0.7) / PI, "V")},
    lesson=Lesson(objetivo="Converter AC em DC pulsante.",
                  teoria=["O diodo de silício conduz acima de ~0,6–0,7 V, descontando essa queda do pico."],
                  observe=["Somente semiciclos positivos aparecem na saída."],
                  experimentos=["Reduza a amplitude para 1 V e veja a zona morta crescer."]))
def halfwave(p):
    return f"""Vin in 0 SIN(0 {p['a']} {p['f']})
D1 in out DSI
R1 out 0 {p['r']}"""


@circuit(
    id="fullwave_bridge", name="Retificador de onda completa (ponte)", category="basicos",
    summary="Quatro diodos aproveitam os dois semiciclos.",
    params=[Param("r", "Carga", 1e3, "Ω", 1, 1e6), Param("a", "Amplitude de pico", 10.0, "V", 1, 400), Param("f", "Frequência", 60.0, "Hz", 1, 1e5)],
    analyses=_rect_an, probes=["vl"],
    theory=lambda p: {"Pico na carga (−2×0,7 V)": (p["a"] - 1.4, "V"), "Valor médio ≈ 2Vp/π": (2 * (p["a"] - 1.4) / PI, "V")},
    lesson=Lesson(objetivo="Entender a ponte retificadora de Graetz.",
                  teoria=["Em cada semiciclo dois diodos conduzem em série com a carga: queda de ~1,4 V."],
                  observe=["A tensão na carga (vl) tem o dobro da frequência da entrada."],
                  experimentos=["Compare a média com a do meia-onda: é o dobro."]))
def bridge(p):
    return f"""Vin ac1 ac2 SIN(0 {p['a']} {p['f']})
Rgnd ac2 0 1e9
D1 ac1 outp DSI
D2 ac2 outp DSI
D3 outn ac1 DSI
D4 outn ac2 DSI
RL outp outn {p['r']}
Rref outn 0 1e9
Bvl vl 0 V=V(outp)-V(outn)"""


@circuit(
    id="inverting_opamp", name="Amplificador inversor (amp-op)", category="basicos",
    summary="Ganho fechado = −Rf/Rin.",
    params=[Param("rin", "Rin", 10e3, "Ω", 100, 1e7), Param("rf", "Rf", 100e3, "Ω", 100, 1e7),
            Param("a", "Amplitude", 0.1, "V", 0.001, 5), Param("f", "Frequência", 1e3, "Hz", 1, 1e6)],
    analyses=lambda p: {"Transient": tran(p["f"], 5), "AC (Bode)": ac(10, 1e7)}, probes=["in", "out"],
    theory=lambda p: {"Ganho": (-p["rf"] / p["rin"], "V/V"), "Ganho (dB)": (20 * math.log10(p["rf"] / p["rin"]), "dB"),
                      "Banda ≈ GBW/|1+Rf/Rin|": (1e6 / (1 + p["rf"] / p["rin"]), "Hz")},
    lesson=Lesson(objetivo="Aprender realimentação negativa e o 'terra virtual'.",
                  teoria=["Com ganho de malha aberta enorme, vn ≈ 0 V; a corrente de Rin passa toda por Rf.",
                          "A banda diminui quando o ganho aumenta (produto ganho × banda constante)."],
                  observe=["Saída invertida (180°) e 10× maior com os valores padrão."],
                  experimentos=["Aumente Rf até a saída saturar perto de ±14 V."]))
def inv_opamp(p):
    return f"""Vcc vcc 0 DC 15
Vee vee 0 DC -15
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
Rin in vn {p['rin']}
Rf vn out {p['rf']}
XU1 0 vn out vcc vee OPAMP"""


@circuit(
    id="noninverting_opamp", name="Amplificador não-inversor (amp-op)", category="basicos",
    summary="Ganho = 1 + R2/R1, alta impedância de entrada.",
    params=[Param("r1", "R1 (ao terra)", 10e3, "Ω", 100, 1e7), Param("r2", "R2 (realimentação)", 90e3, "Ω", 100, 1e7),
            Param("a", "Amplitude", 0.1, "V", 0.001, 5), Param("f", "Frequência", 1e3, "Hz", 1, 1e6)],
    analyses=lambda p: {"Transient": tran(p["f"], 5), "AC (Bode)": ac(10, 1e7)}, probes=["in", "out"],
    theory=lambda p: {"Ganho": (1 + p["r2"] / p["r1"], "V/V")},
    lesson=Lesson(objetivo="Amplificar sem inverter a fase.",
                  teoria=["O divisor R2/R1 devolve parte da saída ao terminal inversor; vn segue vin."],
                  observe=["Saída em fase com a entrada."],
                  experimentos=["R2 = 0 Ω resulta em seguidor de tensão (ganho 1)."]))
def noninv_opamp(p):
    return f"""Vcc vcc 0 DC 15
Vee vee 0 DC -15
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
R2 out vn {p['r2']}
R1 vn 0 {p['r1']}
XU1 in vn out vcc vee OPAMP"""


def _ce_dc(p):
    vb = p["vcc"] * p["r2"] / (p["r1"] + p["r2"])
    ve = max(vb - 0.65, 0.0)
    ic = ve / p["re"]
    return vb, ve, ic


@circuit(
    id="common_emitter", name="Amplificador emissor-comum (BJT)", category="basicos",
    summary="Polarização por divisor de tensão, capacitor de bypass no emissor.",
    params=[Param("r1", "R1 (base, ao Vcc)", 47e3, "Ω", 1e3, 1e7), Param("r2", "R2 (base, ao terra)", 10e3, "Ω", 1e3, 1e7),
            Param("rc", "RC", 2.2e3, "Ω", 100, 1e6), Param("re", "RE", 470.0, "Ω", 10, 1e5), Param("vcc", "Vcc", 12.0, "V", 3, 60),
            Param("a", "Amplitude de entrada", 0.005, "V", 0.0001, 0.2), Param("f", "Frequência", 1e3, "Hz", 10, 1e6)],
    analyses=lambda p: {"Transient": tran(p["f"], 5), "AC (Bode)": ac(10, 1e7), "Ponto de operação": OP}, probes=["in", "out", "c"],
    theory=lambda p: {"VB (divisor)": (_ce_dc(p)[0], "V"), "VE": (_ce_dc(p)[1], "V"), "IC ≈ VE/RE": (_ce_dc(p)[2], "A"),
                      "Ganho ≈ −RC/re' (re'=26mV/IC)": (-p["rc"] / (0.026 / max(_ce_dc(p)[2], 1e-9)), "V/V")},
    lesson=Lesson(objetivo="Projetar o ponto de operação (Q) e o ganho de um estágio a transistor.",
                  teoria=["VB vem do divisor R1/R2; VE = VB − 0,65 V; IC ≈ VE/RE.",
                          "Com CE de bypass, o ganho AC é ≈ −RC/re' onde re' = 26 mV/IC."],
                  observe=["Saída invertida; veja o nó 'c' (coletor) com nível DC em torno de Vcc/2."],
                  experimentos=["Remova o bypass (mude o netlist) e compare o ganho: cai para ≈ −RC/RE."]))
def common_emitter(p):
    return f"""Vcc vcc 0 DC {p['vcc']}
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
Cin in b 10u
R1 vcc b {p['r1']}
R2 b 0 {p['r2']}
Rc vcc c {p['rc']}
Re e 0 {p['re']}
Ce e 0 100u
Q1 c b e QN2222
Cout c out 10u
Rl out 0 100k
.nodeset v(c)={p['vcc']/2}"""


# --- 555 comportamental --------------------------------------------------
NE555 = """
.subckt NE555 gnd trig out rst ctrl thr dis vcc
R1 vcc ctrl 5k
R2 ctrl low 5k
R3 low gnd 5k
Ssh qm gnd thr ctrl SWCMP
Sst qm vcc low trig SWCMP
Cm qm gnd 1n
Bq q gnd V=(V(qm)>0.5*V(vcc)) && (V(rst)>0.7) ? 1 : 0
Bqn qn gnd V=1-V(q)
Bo oi gnd V=V(q)*V(vcc)
Ro oi out 10
Sd dis gnd qn gnd SWM
Rrst rst gnd 1e9
.ends NE555
"""


def f555(p):
    return 1.44 / ((p["ra"] + 2 * p["rb"]) * p["c"])


@circuit(
    id="astable_555", name="Oscilador astável 555", category="basicos",
    summary="Multivibrador com modelo comportamental do CI 555 (comparadores + flip-flop).",
    params=[Param("ra", "RA", 10e3, "Ω", 100, 1e7), Param("rb", "RB", 10e3, "Ω", 100, 1e7), Param("c", "C", 100e-9, "F", 1e-11, 1e-3),
            Param("vcc", "Vcc", 5.0, "V", 3, 15)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / f555(p) / 400, "stop": 6 / f555(p), "maxstep": 1 / f555(p) / 400}},
    probes=["out", "thr"],
    theory=lambda p: {"Frequência f = 1,44/((RA+2RB)C)": (f555(p), "Hz"),
                      "Duty cycle (RA+RB)/(RA+2RB)": ((p["ra"] + p["rb"]) / (p["ra"] + 2 * p["rb"]), "")},
    lesson=Lesson(objetivo="Gerar clock com o 555.",
                  teoria=["C carrega por RA+RB até 2/3 Vcc e descarrega por RB até 1/3 Vcc.",
                          "tH = 0,693(RA+RB)C; tL = 0,693·RB·C."],
                  observe=["thr oscila entre 1/3 e 2/3 de Vcc; out é a onda quadrada."],
                  experimentos=["Faça RA pequeno e veja o duty cycle chegar perto de 50 %."]))
def astable_555(p):
    return f"""{NE555}
Vcc vcc 0 DC {p['vcc']}
Ra vcc dis {p['ra']}
Rb dis thr {p['rb']}
C1 thr 0 {p['c']}
Xu 0 thr out vcc ctl thr dis vcc NE555
Cctl ctl 0 10n
Rl out 0 10k"""
