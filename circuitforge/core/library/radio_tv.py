"""Rádio, TV e som: detector AM, sintonia LC, misturador super-heteródino, sincronismo de TV e oscilador Colpitts."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, ac, circuit, tran, tran_time

TWO_PI = "2*3.14159265358979"


@circuit(
    id="am_detector", name="Receptor AM – detector de envoltória", category="radio_tv",
    summary="Diodo + RC recupera o áudio de uma portadora modulada em amplitude.",
    params=[Param("fc", "Portadora", 100e3, "Hz", 20e3, 500e3), Param("fm", "Áudio modulante", 1e3, "Hz", 100, 5e3),
            Param("m", "Índice de modulação", 0.6, "", 0.1, 1.0), Param("r", "R de detecção", 10e3, "Ω", 1e3, 1e6),
            Param("c", "C de detecção", 10e-9, "F", 1e-10, 1e-6)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["fc"] / 40, "stop": 4 / p["fm"], "maxstep": 1 / p["fc"] / 40}},
    probes=["rf", "det", "audio"],
    theory=lambda p: {"τ = R·C": (p["r"] * p["c"], "s"), "Condição 1/fc ≪ τ ≪ 1/fm": (1.0 if 3 / p["fc"] < p["r"] * p["c"] < 0.3 / p["fm"] else 0.0, "1 = OK"),
                      "τ máximo sem distorção (diagonal clipping)": (math.sqrt(1 - p["m"] ** 2) / (2 * PI * p["fm"] * p["m"]), "s")},
    lesson=Lesson(objetivo="Entender como um rádio AM extrai o som da onda de rádio.",
                  teoria=["O diodo retifica a portadora; o capacitor segura o pico entre ciclos, seguindo o envelope.",
                          "Se τ for grande demais, o detector não acompanha as quedas do envelope (distorção 'diagonal clipping'); se pequeno demais, sobra ondulação da portadora."],
                  observe=["'det' reproduz o envelope; 'audio' é o sinal sem DC."],
                  experimentos=["Aumente C para 100 nF e veja o áudio distorcer.", "Aumente a modulação para 1,0."]))
def am_det(p):
    return f"""Bam rf0 0 V=(1+{p['m']}*sin({TWO_PI}*{p['fm']}*time))*sin({TWO_PI}*{p['fc']}*time)
Rs rf0 rf 1k
D1 rf det D1N4148
Rd det 0 {p['r']}
Cd det 0 {p['c']}
Cc det audio 1u
Ra audio 0 100k"""


def _lc_f0(p):
    return 1 / (2 * PI * math.sqrt(p["l"] * p["cvar"] * 1e-12))


@circuit(
    id="lc_tuner", name="Sintonia de rádio (circuito LC paralelo)", category="radio_tv",
    summary="Capacitor variável desloca a ressonância e seleciona a estação: f0 = 1/(2π√LC).",
    params=[Param("l", "Indutância da antena (ferrite)", 240e-6, "H", 1e-6, 1e-2), Param("cvar", "Capacitor variável", 100.0, "pF", 10, 500),
            Param("rs", "Impedância da antena", 50e3, "Ω", 1e3, 1e6)],
    analyses=lambda p: {"AC (Bode)": ac(200e3, 5e6, 60)}, probes=["tank"],
    theory=lambda p: {"Frequência sintonizada f0": (_lc_f0(p), "Hz"),
                      "Q ≈ Rs/(2πf0L)": (p["rs"] / (2 * PI * _lc_f0(p) * p["l"]), ""),
                      "Banda AM": (1.0 if 530e3 <= _lc_f0(p) <= 1.7e6 else 0.0, "1 = dentro da banda AM")},
    lesson=Lesson(objetivo="Entender a sintonia de estações.",
                  teoria=["Na ressonância a impedância do tanque é máxima, e o sinal dessa frequência aparece amplificado em relação às demais.",
                          "Girar o capacitor variável move f0 (como o dial dos rádios antigos)."],
                  observe=["O pico da curva coincide com f0."],
                  experimentos=["C = 365 pF → 540 kHz. C = 40 pF → 1,6 MHz (usando L = 240 µH).", "Reduza a impedância da antena e veja a seletividade (Q) cair."]))
def tuner(p):
    return f"""Vin in 0 AC 1
Rs in tank {p['rs']}
L1 tank 0 {p['l']}
C1 tank 0 {p['cvar']*1e-12:.6g}
Rloss tank 0 1e9"""


@circuit(
    id="superhet_mixer", name="Misturador do receptor super-heteródino (RF × LO → FI)", category="radio_tv",
    summary="Multiplicador gera soma e diferença de frequências; o tanque LC seleciona a FI de 455 kHz.",
    params=[Param("frf", "Frequência da estação (RF)", 1.0e6, "Hz", 6e5, 1.6e6), Param("fif", "FI", 455e3, "Hz", 200e3, 500e3)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / (p["frf"] + p["fif"]) / 25, "stop": 250e-6, "maxstep": 1 / (p["frf"] + p["fif"]) / 25}},
    probes=["rf", "mix", "if"],
    theory=lambda p: {"LO = RF + FI": (p["frf"] + p["fif"], "Hz"), "Frequência-imagem = RF + 2·FI": (p["frf"] + 2 * p["fif"], "Hz"),
                      "Soma RF+LO": (2 * p["frf"] + p["fif"], "Hz")},
    lesson=Lesson(objetivo="Entender o coração do rádio super-heteródino.",
                  teoria=["O produto sen(a)·sen(b) contém sen(a−b) e sen(a+b). O filtro de FI deixa só a diferença (LO − RF = 455 kHz).",
                          "Assim todos os canais viram a mesma FI, onde o filtro é fixo e muito seletivo.",
                          "Uma estação na frequência-imagem (RF + 2·FI) também cairia na FI: o filtro de RF precisa rejeitá-la."],
                  observe=["Use o analisador de espectro em 'mix' e em 'if'."],
                  experimentos=["Troque a RF por 1,91 MHz com LO fixo (edite o netlist): é a frequência-imagem."]))
def superhet(p):
    flo = p["frf"] + p["fif"]
    L = 100e-6
    C = 1 / ((2 * PI * p["fif"]) ** 2 * L)
    return f"""Vrf rf 0 SIN(0 0.1 {p['frf']})
Vlo lo 0 SIN(0 1 {flo})
Bmix mix 0 V=V(rf)*V(lo)
Rm mix if 10k
L1 if 0 {L}
C1 if 0 {C:.6g}
Rq if 0 60k"""


@circuit(
    id="tv_sync_separator", name="Separador de sincronismo de TV (vídeo composto)", category="radio_tv",
    summary="Extrai os pulsos de sincronismo horizontal (15,73 kHz) do sinal de vídeo composto.",
    params=[Param("slice", "Nível de corte", -0.25, "V", -0.55, 0.0), Param("amp", "Amplitude do vídeo", 0.65, "V", 0.3, 1.5)],
    analyses=lambda p: {"Transient": tran_time(10 * 63.55e-6, 10000)}, probes=["vid", "k", "sync"],
    theory=lambda p: {"Frequência de linha (NTSC)": (15734.0, "Hz"), "Período da linha": (63.55e-6, "s"), "Largura do sync": (4.7e-6, "s")},
    lesson=Lesson(objetivo="Entender como a TV analógica mantém a imagem estável.",
                  teoria=["O sinal de vídeo composto tem os pulsos de sincronismo 'abaixo do preto'. Um grampo (clamp) com diodo fixa o topo do sync e um comparador corta nesse nível.",
                          "A saída 'sync' dispara o oscilador horizontal que varre o feixe do cinescópio."],
                  observe=["'k' mostra o vídeo grampeado; 'sync' são pulsos de 4,7 µs a cada 63,55 µs."],
                  experimentos=["Aumente o nível de corte para -0.05 V e veja o vídeo vazar para o sync."]))
def sync_sep(p):
    return f"""Vbase base 0 PULSE(0 {p['amp']} 4.7u 100n 100n 58.6u 63.55u)
Bvid vid 0 V=V(base)+0.12*sin({TWO_PI}*600k*time)*(V(base)>0.3 ? 1 : 0)
Cc vid k 2.2n
Dcl 0 k DSI
Rk k 0 100k
Bsync sync 0 V=V(k)<{p['slice']} ? 5 : 0"""


def _colpitts_f(p):
    return 1 / (2 * PI * math.sqrt(p["l"] * (p["c1"] * p["c2"] / (p["c1"] + p["c2"]))))


@circuit(
    id="colpitts_oscillator", name="Oscilador Colpitts (oscilador local de rádio)", category="radio_tv",
    summary="Transistor + tanque LC com divisor capacitivo: gera a portadora de RF.",
    params=[Param("l", "L", 10e-6, "H", 1e-7, 1e-3), Param("c1", "C1", 1e-9, "F", 1e-11, 1e-6), Param("c2", "C2", 1e-9, "F", 1e-11, 1e-6)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / _colpitts_f(p) / 40, "stop": 120 / _colpitts_f(p), "maxstep": 1 / _colpitts_f(p) / 40}},
    probes=["c", "e"],
    theory=lambda p: {"f0 = 1/(2π√(L·C1C2/(C1+C2)))": (_colpitts_f(p), "Hz"), "Condição de partida gm·Re' > C2/C1": (p["c2"] / p["c1"], "")},
    lesson=Lesson(objetivo="Entender como um rádio gera sua frequência local.",
                  teoria=["O divisor C1–C2 realimenta parte do sinal do tanque para o emissor (base em comum). Com ganho suficiente o circuito oscila na ressonância do tanque.",
                          "A amplitude estabiliza quando o transistor entra em não-linearidade (corte)."],
                  observe=["Veja a oscilação crescer exponencialmente a partir do pulso inicial."],
                  experimentos=["Mude C1 e C2 para 470 pF: f0 sobe para ≈ 3,3 MHz."]))
def colpitts(p):
    return f"""Vcc vcc 0 DC 9
L1 vcc c {p['l']}
Q1 c b e QN2222
R1 vcc b 47k
R2 b 0 15k
Cb b 0 10n
Re e 0 1k
C1 c e {p['c1']}
C2 e 0 {p['c2']}
Ikick 0 c PULSE(0 2m 0 5n 5n 40n 1)
Rl c 0 100k"""
