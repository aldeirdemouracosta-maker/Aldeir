"""Circuitos para IA: neurônio analógico, crossbar, front-end de sensor, VRM de acelerador."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, OP, ac, circuit, dc, tran_time
from .fontes import buck_netlist


@circuit(
    id="analog_neuron", name="Neurônio analógico (soma ponderada + tanh)", category="ia",
    summary="Amp-op somador (pesos = Rf/Ri) seguido de par diferencial BJT, que realiza a ativação ≈ tanh.",
    params=[Param("w1", "Peso w1", 1.0, "", -5, 5), Param("w2", "Peso w2", 0.5, "", -5, 5), Param("x2", "Entrada x2 fixa", 0.2, "V", -2, 2),
            Param("bias", "Viés (bias)", 0.0, "V", -2, 2), Param("gain", "Escala de entrada do par diferencial", 5.0, "", 0.5, 30)],
    analyses=lambda p: {"Curva de ativação (x1 de −2 a 2 V)": dc("Vx1", -2, 2, 0.05)}, probes=["s", "act", "out"],
    theory=lambda p: {"Saturação (±Ic·Rc)": (1e-3 * 4.7e3, "V"), "Inclinação em x1=0 ≈ gain·w1·Ic·Rc/(2·Vt)": (p["gain"] * p["w1"] * 1e-3 * 4.7e3 / 0.052, "V/V")},
    lesson=Lesson(objetivo="Mostrar como um neurônio artificial y = f(Σ wᵢxᵢ + b) vira hardware analógico.",
                  teoria=["Os pesos são razões de resistores: wᵢ = Rf/Rᵢ. O amp-op soma (e inverte) as correntes.",
                          "O par diferencial BJT converte a diferença de tensão em corrente com curva tanh: é a função de ativação.",
                          "Aceleradores de IA analógicos/in-memory usam exatamente esta ideia, com memristores no lugar dos resistores."],
                  observe=["'s' é a soma linear; 'out' satura suavemente (sigmoide)."],
                  experimentos=["Mude w1 para negativo e veja a curva invertida.", "Mude o viés para deslocar o limiar."]))
def neuron(p):
    rf = 10e3
    r1 = rf / max(abs(p["w1"]), 1e-3)
    r2 = rf / max(abs(p["w2"]), 1e-3)
    # sinal do peso: usa entrada invertida (-x) para pesos negativos
    s1 = "x1" if p["w1"] >= 0 else "nx1"
    s2 = "x2" if p["w2"] >= 0 else "nx2"
    # o somador inverte; o estágio seguinte (ganho -1) restaura o sinal
    return f"""Vcc vcc 0 DC 12
Vee vee 0 DC -12
Vx1 x1 0 DC 0
Vx2 x2 0 DC {p['x2']}
Vb bsrc 0 DC {p['bias']}
Enx1 nx1 0 x1 0 -1
Enx2 nx2 0 x2 0 -1
R1 {s1} sm {r1:.6g}
R2 {s2} sm {r2:.6g}
Rb bsrc sm 10k
Rf1 sm so {rf}
XU1 0 sm so vcc vee OPAMP
Rinv1 so si 10k
Rinv2 si s 10k
XU2 0 si s vcc vee OPAMP
Eact act 0 s 0 {p['gain']/10:.6g}
Q1 c1 act e QN2222
Q2 c2 0 e QN2222
Itail e vee DC 2m
Vcc2 vcc2 0 DC 12
Rc1 vcc2 c1 4.7k
Rc2 vcc2 c2 4.7k
Bout out 0 V=V(c2)-V(c1)"""


MATRIX = [[1.0, 0.5], [0.25, 1.0], [0.5, 0.25]]   # condutâncias relativas (mS)


@circuit(
    id="crossbar_mvm", name="Crossbar resistivo – multiplicação matriz-vetor analógica", category="ia",
    summary="Matriz 3×2 de condutâncias + conversores corrente-tensão: Iⱼ = Σ Gᵢⱼ·Vᵢ pela lei de Ohm e Kirchhoff.",
    params=[Param("v1", "Entrada V1", 0.5, "V", -1, 1), Param("v2", "Entrada V2", -0.3, "V", -1, 1), Param("v3", "Entrada V3", 0.8, "V", -1, 1),
            Param("rf", "Resistor de realimentação", 1e3, "Ω", 100, 1e5)],
    analyses=lambda p: {"Ponto de operação": OP}, probes=["y1", "y2"],
    theory=lambda p: {f"y{j+1} = −Rf·Σ Gᵢⱼ·Vᵢ": (-p["rf"] * sum(MATRIX[i][j] * 1e-3 * [p["v1"], p["v2"], p["v3"]][i] for i in range(3)), "V") for j in range(2)},
    lesson=Lesson(objetivo="Entender a computação em memória (in-memory computing) usada em chips de IA.",
                  teoria=["Cada cruzamento linha-coluna é um resistor (peso = condutância G). A corrente de cada coluna é a soma de Gᵢⱼ·Vᵢ: um produto matriz-vetor em um único passo.",
                          "O amp-op transimpedância converte a corrente da coluna em tensão. Redes neurais são principalmente multiplicações matriz-vetor.",
                          "Na prática G é uma memória (memristor/ReRAM/flash) programável."],
                  observe=["As saídas y1, y2 coincidem com o cálculo matricial teórico."],
                  experimentos=["Mude as entradas e verifique linearidade (superposição)."]))
def crossbar(p):
    lines = ["Vcc vcc 0 DC 12", "Vee vee 0 DC -12",
             f"V1 in1 0 DC {p['v1']}", f"V2 in2 0 DC {p['v2']}", f"V3 in3 0 DC {p['v3']}"]
    for i in range(3):
        for j in range(2):
            g = MATRIX[i][j] * 1e-3
            lines.append(f"Rg{i+1}{j+1} in{i+1} col{j+1} {1/g:.6g}")
    for j in range(2):
        lines += [f"Rfb{j+1} col{j+1} y{j+1} {p['rf']}", f"XU{j+1} 0 col{j+1} y{j+1} vcc vee OPAMP"]
    return "\n".join(lines)


def _sk(p):
    return 1 / (2 * PI * math.sqrt(p["r"] * p["r"] * p["c1"] * p["c2"]))


@circuit(
    id="sensor_frontend", name="Front-end de sensor para IA de borda (pré-amp + anti-aliasing)", category="ia",
    summary="Microfone → amplificador → filtro Sallen-Key passa-baixa de 2ª ordem antes do ADC de um TinyML.",
    params=[Param("r", "R do filtro", 10e3, "Ω", 100, 1e6), Param("c1", "C1", 2.2e-9, "F", 1e-12, 1e-6), Param("c2", "C2", 1.1e-9, "F", 1e-12, 1e-6),
            Param("gain", "Ganho do pré-amp", 20.0, "V/V", 1, 200)],
    analyses=lambda p: {"AC (Bode)": ac(10, 1e6, 30), "Transient": tran_time(2e-3, 4000)}, probes=["in", "pre", "out"],
    theory=lambda p: {"Corte do Sallen-Key fc": (_sk(p), "Hz"), "Q (R iguais)": (math.sqrt(p["c1"] / p["c2"]) / 2, ""),
                      "Ganho do pré-amp": (p["gain"], "V/V")},
    lesson=Lesson(objetivo="Preparar um sinal analógico para ser amostrado por um microcontrolador com IA embarcada.",
                  teoria=["Sem filtro anti-aliasing, frequências acima de fs/2 se dobram sobre a banda útil.",
                          "O Sallen-Key com C1/C2 = 2 e R iguais dá resposta de Butterworth (Q = 0,707)."],
                  observe=["Queda de 40 dB/década acima de fc."],
                  experimentos=["Para ADC de 16 kHz (fs/2 = 8 kHz) ajuste fc ≈ 6 kHz."]))
def frontend(p):
    return f"""Vcc vcc 0 DC 12
Vee vee 0 DC -12
Vin in 0 SIN(0 0.01 1k) AC 1
XU1 in vn pre vcc vee OPAMP
Rg vn 0 1k
Rfg pre vn {(p['gain']-1)*1e3:.6g}
R1 pre a {p['r']}
R2 a b {p['r']}
C1 a out {p['c1']}
C2 b 0 {p['c2']}
XU2 b out out vcc vee OPAMP"""


@circuit(
    id="accelerator_vrm", name="VRM de acelerador de IA/GPU (degrau de 20 A a 120 A)", category="ia",
    summary="Fonte de núcleo de acelerador: 4 fases entrelaçadas alimentando carga que muda quase instantaneamente.",
    params=[Param("vin", "Entrada", 12.0, "V", 5, 20), Param("vout", "Tensão do núcleo", 0.85, "V", 0.5, 1.5),
            Param("l", "Indutor por fase", 150e-9, "H", 30e-9, 2e-6), Param("c", "Capacitância total de saída", 1.5e-3, "F", 100e-6, 1e-2),
            Param("i1", "Corrente inicial", 20.0, "A", 1, 200), Param("i2", "Corrente de pico", 120.0, "A", 1, 300)],
    analyses=lambda p: {"Degrau de carga": {"kind": "tran", "step": 1 / 400e3 / 80, "stop": 60 / 400e3, "maxstep": 1 / 400e3 / 80, "uic": True}},
    probes=["out"],
    theory=lambda p: {"Corrente por fase (pico)": (p["i2"] / 4, "A"), "Potência no núcleo": (p["vout"] * p["i2"], "W"),
                      "Frequência de ondulação (4 fases)": (4 * 400e3, "Hz")},
    lesson=Lesson(objetivo="Dimensionar a alimentação de placas aceleradoras de IA.",
                  teoria=["Cargas de IA variam de 20 A a 120 A em microssegundos (di/dt enorme). Capacitância de saída e fases múltiplas seguram a tensão.",
                          "O afundamento inicial ≈ ΔI·ESR + ΔI·(L_eq/…) é a métrica crítica: se o núcleo cair demais, o chip trava."],
                  observe=["O afundamento da tensão no degrau e a ondulação a 1,6 MHz."],
                  experimentos=["Dobre a capacitância e compare o afundamento.", "Reduza para 2 fases comparando mentalmente: as correntes por fase dobram."]))
def acc_vrm(p):
    return buck_netlist(p["vin"], p["vout"], 400e3, p["l"], p["c"], 0.0005, 1.0, phases=4,
                        i_step=(p["i1"], p["i2"]), t_step=25 / 400e3, vdrop=p["i1"] * 0.003 / 4, sync=True)
