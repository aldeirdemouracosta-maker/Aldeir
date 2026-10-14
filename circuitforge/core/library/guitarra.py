"""Pedais de guitarra: boost, overdrive, fuzz, wah e tremolo."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, tran, tran_time


@circuit(
    id="clean_boost", name="Pedal Clean Boost (1 transistor)", category="guitarra",
    summary="Emissor-comum com ganho ajustável por degeneração parcial do emissor, alimentado por bateria de 9 V.",
    params=[Param("re1", "Re não-bypassado", 100.0, "Ω", 0, 1e3), Param("a", "Sinal da guitarra (pico)", 0.1, "V", 0.005, 1),
            Param("f", "Frequência", 440.0, "Hz", 50, 5e3)],
    analyses=lambda p: {"Transient": tran(p["f"], 6), "AC (Bode)": ac(10, 1e6, 30)}, probes=["in", "out"],
    theory=lambda p: {"Ganho aproximado": (-3.3e3 / (p["re1"] + 7.5), "V/V")},
    lesson=Lesson(objetivo="Entender o booster: mais nível sem alterar o timbre.",
                  teoria=["O ganho de um emissor-comum com degeneração é ≈ Rc/(re' + Re1).", "Re1 maior = menos ganho e menos distorção."],
                  observe=["Com Re1 = 0 a saída satura e distorce suavemente."],
                  experimentos=["Compare Re1 = 0, 100 e 470 Ω."]))
def boost(p):
    return f"""Vcc vcc 0 DC 9
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
Cin in b 100n
R1 vcc b 470k
R2 b 0 100k
Rc vcc c 3.3k
Re1 e e2 {max(p['re1'], 0.01)}
Re2 e2 0 1k
Ce e2 0 100u
Q1 c b e QN2222
Cout c out 1u
Rl out 0 1Meg"""


@circuit(
    id="overdrive_ts", name="Overdrive estilo Tube Screamer (amp-op + diodos)", category="guitarra",
    summary="Amp-op com diodos em antiparalelo na realimentação: compressão suave e 'saturação de válvula'.",
    params=[Param("drive", "Drive (potenciômetro)", 100e3, "Ω", 0, 500e3), Param("a", "Sinal da guitarra (pico)", 0.15, "V", 0.005, 1),
            Param("f", "Frequência", 440.0, "Hz", 50, 5e3)],
    analyses=lambda p: {"Transient": tran(p["f"], 8, 300), "AC (Bode, sinal pequeno)": ac(10, 1e5, 30)}, probes=["in", "clip", "out"],
    theory=lambda p: {"Ganho linear 1+(51k+Drive)/4,7k": (1 + (51e3 + p["drive"]) / 4.7e3, "V/V"),
                      "Limitação dos diodos (±)": (0.6, "V"),
                      "Corte do tone (220 Ω+1 kΩ, 220 nF)": (1 / (2 * PI * 1220 * 220e-9), "Hz")},
    lesson=Lesson(objetivo="Entender como pedais de overdrive criam distorção.",
                  teoria=["O amp-op amplifica o sinal; os diodos de silício em antiparalelo limitam a tensão de realimentação a ≈ ±0,6 V, 'achatando' os picos.",
                          "O capacitor em série com Rg corta graves do ganho (o característico 'mid hump').",
                          "O filtro RC de saída (tone) suaviza os harmônicos agudos."],
                  observe=["O nó 'clip' mostra o topo achatado; 'out' é suavizado pelo filtro."],
                  experimentos=["Drive em 0: quase limpo. Drive em 500 kΩ: saturação pesada.", "Troque os diodos por LEDs (edite o netlist) e veja mais headroom."]))
def overdrive(p):
    return f"""Vcc vcc 0 DC 9
Rb1 vcc vb 10k
Rb2 vb 0 10k
Cb vb 0 47u
Vin in 0 SIN(0 {p['a']} {p['f']}) AC 1
Cin in n1 22n
Rin n1 inp 10k
Rg1 inp vb 510k
XU1 inp inn clip vcc 0 OPAMP
Rg inn g1 4.7k
Cg g1 vb 47n
Rf clip inn {51e3 + p['drive']:.6g}
Cf clip inn 51p
D1 clip inn D1N4148
D2 inn clip D1N4148
Rt clip t 1.22k
Ct t vb 220n
Cout t out 1u
Rl out 0 100k"""


@circuit(
    id="fuzz_face", name="Fuzz Face (2 transistores com realimentação)", category="guitarra",
    summary="Dois transistores com realimentação CC criam um som saturado e 'rasgado'.",
    params=[Param("fuzz", "Fuzz (resistor de emissor Q1)", 100.0, "Ω", 0, 1e3), Param("bf", "Beta dos transistores", 150.0, "", 30, 400),
            Param("a", "Sinal da guitarra (pico)", 0.1, "V", 0.005, 0.5), Param("f", "Frequência", 220.0, "Hz", 50, 2e3)],
    analyses=lambda p: {"Transient": tran(p["f"], 8, 300)}, probes=["in", "c1", "out"],
    theory=lambda p: {"Realimentação CC Q2→Q1": (100e3, "Ω")},
    lesson=Lesson(objetivo="Entender um clássico dos anos 60.",
                  teoria=["Q1 amplifica e inverte; Q2 inverte de novo. O resistor de 100 kΩ polariza Q1 a partir do coletor de Q2.",
                          "A alta realimentação e o ganho enorme levam os transistores à saturação e ao corte: onda quase quadrada, rica em harmônicos."],
                  observe=["A onda de entrada de 100 mV vira quase quadrada na saída."],
                  experimentos=["Aumente o resistor de emissor de Q1 (menos fuzz) e reduza o beta (mais 'gate')."],
                  cuidados=["Os originais usam germânio PNP, sensíveis à temperatura. Este modelo usa silício NPN."]))
def fuzz(p):
    return f""".model QFZ NPN(Is=1e-14 Bf={p['bf']} Vaf=100 Cje=10p Cjc=5p Tf=0.5n)
Vcc vcc 0 DC 9
Vin in 0 SIN(0 {p['a']} {p['f']})
Cin in b1 2.2u
Q1 c1 b1 e1 QFZ
Re1 e1 0 {max(p['fuzz'], 0.1)}
R1 vcc c1 33k
Q2 c2 c1 0 QFZ
R2 vcc c2 8.2k
Rfb c2 b1 100k
Cout c2 out 100n
Rvol out 0 100k"""


def _wah_f(pos):
    return 400 * (5.5 ** pos)


@circuit(
    id="wah_pedal", name="Pedal Wah-Wah (filtro ressonante LC)", category="guitarra",
    summary="Filtro passa-faixa LC cuja frequência de pico varia com a posição do pedal (400 Hz a 2,2 kHz).",
    params=[Param("pos", "Posição do pedal (0 = calcanhar, 1 = ponta)", 0.5, "", 0, 1), Param("rs", "Resistência de fonte (define Q)", 22e3, "Ω", 1e3, 200e3)],
    analyses=lambda p: {"AC (Bode)": ac(50, 20e3, 60)}, probes=["wah"],
    theory=lambda p: {"Frequência do pico f0": (_wah_f(p["pos"]), "Hz"),
                      "Q aproximado": (p["rs"] / (2 * PI * _wah_f(p["pos"]) * 0.5), "")},
    lesson=Lesson(objetivo="Entender o efeito de 'wah' como filtro passa-faixa móvel.",
                  teoria=["O indutor de 500 mH em paralelo com C ressoa em f0 = 1/(2π√LC). O pedal muda o C efetivo.",
                          "Quanto maior a resistência de fonte, maior Q e mais pronunciado o 'wow'."],
                  observe=["Varie 'pos' e compare a posição do pico no Bode."],
                  experimentos=["Aumente rs para 100 kΩ: pico mais estreito."]))
def wah(p):
    f0 = _wah_f(p["pos"])
    L = 0.5
    C = 1 / ((2 * PI * f0) ** 2 * L)
    return f"""Vin in 0 AC 1
Rs in w {p['rs']}
L1 w 0 {L} 
Rl1 w 0 1e9
C1 w 0 {C:.6g}
Ebuf wah 0 w 0 1
Rout wah 0 100k"""


@circuit(
    id="tremolo", name="Tremolo (LFO + amplificador controlado por tensão)", category="guitarra",
    summary="Um oscilador de baixa frequência modula o ganho do sinal da guitarra.",
    params=[Param("rate", "Velocidade", 5.0, "Hz", 0.5, 15), Param("depth", "Profundidade", 0.8, "", 0, 1),
            Param("a", "Sinal da guitarra (pico)", 0.2, "V", 0.01, 1), Param("f", "Nota", 440.0, "Hz", 100, 2e3)],
    analyses=lambda p: {"Transient": tran_time(1.0 / p["rate"] * 2, 2 * 40 * int(p["f"] / p["rate"] + 5))}, probes=["in", "out", "lfo"],
    theory=lambda p: {"Período do LFO": (1 / p["rate"], "s"), "Ganho mínimo": (1 - p["depth"], ""), "Modulação (dB)": (20 * math.log10(max(1 - p["depth"], 1e-3)), "dB")},
    lesson=Lesson(objetivo="Ver modulação de amplitude em ação.",
                  teoria=["O ganho varia como g(t) = 1 − depth·(1+sin(2π·rate·t))/2. Nos pedais reais isso é feito por um OTA, JFET ou LDR (Vactrol)."],
                  observe=["O envelope da saída oscila na frequência do LFO."],
                  experimentos=["Aumente a velocidade para 12 Hz (efeito vibrato rápido)."]))
def tremolo(p):
    return f"""Vin in 0 SIN(0 {p['a']} {p['f']})
Blfo lfo 0 V=sin(2*3.14159265*{p['rate']}*time)
Bvca out 0 V=V(in)*(1-{p['depth']}*0.5*(1+V(lfo)))
Rl out 0 100k"""
