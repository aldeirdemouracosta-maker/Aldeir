"""Circuitos veiculares: carregador USB, load dump, alternador, relé, LED PWM, proteção de polaridade."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, circuit, tran, tran_time, OP
from .fontes import buck_netlist, _buck_theory


@circuit(
    id="car_usb_charger", name="Carregador USB veicular (12–14,4 V → 5 V / 2,4 A)", category="veiculos",
    summary="Buck de bateria automotiva para USB, com diodo Schottky.",
    params=[Param("vin", "Tensão da bateria/alternador", 13.8, "V", 9, 16), Param("f", "Frequência", 150e3, "Hz", 50e3, 1e6),
            Param("l", "Indutor", 22e-6, "H", 1e-6, 1e-3), Param("c", "Capacitor de saída", 100e-6, "F", 1e-6, 1e-2),
            Param("rl", "Carga (2,4 A ≈ 2,1 Ω)", 2.1, "Ω", 0.5, 100)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 1 / p["f"] / 100, "stop": 200 / p["f"], "maxstep": 1 / p["f"] / 200, "uic": True}},
    probes=["out", "sw0"],
    theory=lambda p: _buck_theory({**p, "vout": 5.0, "esr": 0.02}),
    lesson=Lesson(objetivo="Projetar o carregador de celular do carro.",
                  teoria=["A tensão do alternador varia de 11 a 14,4 V (e tem picos): o conversor deve regular os 5 V da USB.",
                          "O modelo real tem proteção contra picos, filtro EMI e controle em malha fechada."],
                  observe=["A saída de ~5 V com ondulação baixa; 'sw0' é o chaveamento."],
                  experimentos=["Troque a tensão para 9 V e 16 V (partida a frio e alternador carregando)."],
                  cuidados=["Malha aberta: em hardware real o controle ajusta D para manter 5,0 V."]))
def car_usb(p):
    return buck_netlist(p["vin"], 5.0, p["f"], p["l"], p["c"], 0.02, p["rl"], vdrop=0.45)


@circuit(
    id="load_dump_clamp", name="Proteção contra load dump (TVS) na rede 12 V", category="veiculos",
    summary="Quando a bateria é desligada com o alternador carregando, surge um pico de dezenas de volts que destrói eletrônicas sem proteção.",
    params=[Param("peak", "Pico do load dump", 60.0, "V", 20, 120), Param("tvs", "TVS presente (1 = sim)", 1, "", 0, 1),
            Param("vclamp", "Tensão de ruptura do TVS", 24.0, "V", 16, 40), Param("rsrc", "Resistência da fonte (alternador)", 0.6, "Ω", 0.1, 5)],
    analyses=lambda p: {"Transient": tran_time(80e-3, 4000)}, probes=["ecu", "src"],
    theory=lambda p: {"Pico sem proteção": (p["peak"], "V"), "Corrente máx. no TVS ≈ (Vpico−Vz)/Rs": ((p["peak"] - p["vclamp"]) / p["rsrc"], "A")},
    lesson=Lesson(objetivo="Mostrar por que módulos automotivos incluem TVS (norma ISO 7637/16750).",
                  teoria=["Em load dump, a energia armazenada no alternador não tem para onde ir e a tensão sobe até 40–100 V por centenas de ms.",
                          "O TVS conduz acima da tensão de ruptura e desvia a corrente para o terra, limitando o pico visto pela eletrônica."],
                  observe=["Com TVS, 'ecu' fica próxima de 24–30 V; sem TVS, segue a fonte (60 V)."],
                  experimentos=["Mude 'tvs' para 0 e veja a tensão total aplicada ao módulo."],
                  cuidados=["O TVS deve suportar a energia do pulso (J). Verifique o datasheet."]))
def load_dump(p):
    d = (f"Dtvs 0 ecu DTVS" if p["tvs"] >= 0.5 else "Rnotvs 0 ecu 1e9")
    return f""".model DTVS D(Is=1e-12 Bv={p['vclamp']} Ibv=1m Rs=0.25 Cjo=1n)
Vsrc s 0 PULSE(14 {p['peak']} 5m 2m 40m 10m 1)
Rsrc s src {p['rsrc']}
Rcable src ecu 0.05
{d}
Cin ecu 0 10u
Recu ecu 0 100"""


@circuit(
    id="alternator_rectifier", name="Alternador trifásico com ponte retificadora", category="veiculos",
    summary="Três enrolamentos em Y, seis diodos, bateria e carga: a geração de energia do carro.",
    params=[Param("vph", "Pico de fase", 11.0, "V", 6, 40), Param("f", "Frequência elétrica", 300.0, "Hz", 50, 1500),
            Param("vbat", "Bateria", 12.6, "V", 10, 15), Param("rload", "Carga do veículo", 2.0, "Ω", 0.5, 50)],
    analyses=lambda p: {"Transient": tran(p["f"], 14, 300)}, probes=["bus", "a"],
    theory=lambda p: {"Tensão retificada máx. ≈ √3·Vph": (math.sqrt(3) * p["vph"], "V"), "Ondulação a 6·f": (6 * p["f"], "Hz")},
    lesson=Lesson(objetivo="Entender a retificação trifásica do alternador.",
                  teoria=["Cada fase conduz em ±120°; a ponte de 6 diodos entrega ondulação de 6·f com amplitude pequena.",
                          "A tensão do barramento é limitada pela bateria. Acima de ~14,4 V o regulador reduz a excitação."],
                  observe=["O barramento tem uma ondulação pequena; compare com a retificação monofásica."],
                  experimentos=["Reduza a velocidade (f) e veja o alternador deixar de carregar abaixo de certo ponto."]))
def alternator(p):
    return f"""Va a0 n SIN(0 {p['vph']} {p['f']} 0 0 0)
Vb b0 n SIN(0 {p['vph']} {p['f']} 0 0 -120)
Vc c0 n SIN(0 {p['vph']} {p['f']} 0 0 -240)
Rn n 0 1e6
Ra a0 a 0.05
Rb b0 b 0.05
Rc c0 c 0.05
D1 a bus DSI
D2 b bus DSI
D3 c bus DSI
D4 0 a DSI
D5 0 b DSI
D6 0 c DSI
Cbus bus 0 4700u
Rint bus vb 0.03
Vbat vb 0 DC {p['vbat']}
Rload bus 0 {p['rload']}"""


@circuit(
    id="relay_flyback", name="Acionamento de relé com diodo de roda livre", category="veiculos",
    summary="Ao desligar uma bobina, o indutor gera pico de tensão; o diodo flyback o elimina.",
    params=[Param("flyback", "Diodo flyback (1 = sim)", 1, "", 0, 1), Param("l", "Indutância da bobina", 50e-3, "H", 1e-3, 1.0),
            Param("rcoil", "Resistência da bobina", 120.0, "Ω", 20, 1e3), Param("vbat", "Bateria", 12.0, "V", 5, 28)],
    analyses=lambda p: {"Transient": tran_time(24e-3, 12000)}, probes=["drain", "icoil"],
    theory=lambda p: {"Corrente da bobina": (p["vbat"] / p["rcoil"], "A"), "Constante de tempo L/R": (p["l"] / p["rcoil"], "s"),
                      "Energia armazenada ½LI²": (0.5 * p["l"] * (p["vbat"] / p["rcoil"]) ** 2, "J")},
    lesson=Lesson(objetivo="Proteger transistores e módulos contra picos indutivos.",
                  teoria=["A corrente em um indutor não muda instantaneamente: v = L·di/dt. Ao abrir o transistor a tensão sobe até algo romper.",
                          "O diodo em paralelo com a bobina oferece caminho à corrente e limita o pico a ≈ Vbat + 0,7 V."],
                  observe=["Sem diodo o dreno vai a dezenas de volts (limitado aqui pela avalanche a 60 V)."],
                  experimentos=["Compare o pico com e sem diodo."],
                  cuidados=["O diodo de flyback atrasa a liberação do relé; um Zener em série acelera a queda."]))
def relay(p):
    fb = "Dfly drain vbat DSCH" if p["flyback"] >= 0.5 else "Rnofly drain vbat 1e9"
    return f""".model DAV D(Is=1e-14 Bv=60 Ibv=1m Rs=1)
Vbat vbat 0 DC {p['vbat']}
Lcoil vbat cm {p['l']}
Rcoil cm drain {p['rcoil']}
Bi icoil 0 V=I(Vsense)
Vsense drain d2 0
Cpar drain 0 100p
{fb}
Dav 0 drain DAV
Vdrv drv 0 PULSE(0 1 2m 10n 10n 10m 24m)
S1 d2 0 drv 0 SWM"""


@circuit(
    id="led_pwm_dimmer", name="Dimmer PWM para LED (farol/DRL)", category="veiculos",
    summary="MOSFET chaveia um conjunto de LEDs a 500 Hz; a razão cíclica ajusta a luminosidade.",
    params=[Param("duty", "Ciclo de trabalho", 0.5, "", 0.05, 1.0), Param("f", "Frequência PWM", 500.0, "Hz", 100, 5000),
            Param("vbat", "Bateria", 13.8, "V", 9, 16), Param("r", "Resistor limitador", 10.0, "Ω", 1, 100)],
    analyses=lambda p: {"Transient": tran(p["f"], 4, 400)}, probes=["iled", "drain"],
    theory=lambda p: {"Corrente média ≈ D·(Vbat−4·2,1 V)/R": (p["duty"] * max(p["vbat"] - 8.4, 0) / p["r"], "A"),
                      "Brilho relativo": (p["duty"], "")},
    lesson=Lesson(objetivo="Controlar a luminosidade sem perder eficiência em resistor variável.",
                  teoria=["Acima de ~100 Hz o olho integra a luz: brilho médio ∝ razão cíclica.",
                          "O MOSFET opera como chave (baixa perda); o resistor fixa a corrente de pico."],
                  observe=["A corrente 'iled' é retangular com amplitude fixa e largura = D·T."],
                  experimentos=["Reduza a bateria a 9 V (LEDs mal acendem)."]))
def led_pwm(p):
    T = 1 / p["f"]
    return f"""Vbat vbat 0 DC {p['vbat']}
Vsense vbat v1 0
Rlim v1 a1 {p['r']}
D1 a1 a2 DLED
D2 a2 a3 DLED
D3 a3 a4 DLED
D4 a4 drain DLED
M1 drain g 0 0 NMOSP W=1 L=1
Rg g gate 47
Vg gate 0 PULSE(0 12 0 20n 20n {p['duty']*T:.6e} {T:.6e})
Bi iled 0 V=I(Vsense)"""


@circuit(
    id="reverse_polarity", name="Proteção contra inversão de polaridade (PMOS vs diodo)", category="veiculos",
    summary="Um MOSFET canal P em série perde bem menos que um diodo e protege contra bateria invertida.",
    params=[Param("pol", "Polaridade (1 = correta, −1 = invertida)", 1, "", -1, 1), Param("mode", "Proteção (1 = PMOS, 0 = diodo)", 1, "", 0, 1),
            Param("vbat", "Bateria", 12.0, "V", 6, 28), Param("rl", "Carga", 2.0, "Ω", 0.5, 100)],
    analyses=lambda p: {"Transient": tran_time(20e-3, 2000)}, probes=["bat", "load"],
    theory=lambda p: {"Queda no diodo (~0,7 V)": (0.7, "V"), "Perda no diodo": (0.7 * p["vbat"] / p["rl"], "W"),
                      "Perda no PMOS (Rds≈0,1 Ω)": (0.1 * (p["vbat"] / p["rl"]) ** 2, "W")},
    lesson=Lesson(objetivo="Escolher entre diodo e MOSFET na entrada de alimentação veicular.",
                  teoria=["O diodo em série sempre perde ~0,7 V × I. O PMOS com gate no terra conduz pelo canal com Rds(on) baixíssimo.",
                          "Com a bateria invertida, a tensão de gate-fonte fica ≈ 0 e o transistor desliga; o diodo de corpo também está reverso."],
                  observe=["Com pol = −1 a carga fica em 0 V em ambos os casos."],
                  experimentos=["Compare 'load' com pol = 1 usando diodo e PMOS."]))
def revpol(p):
    prot = "M1 bat 0 load load PMOSP W=1 L=1" if p["mode"] >= 0.5 else "Dp bat load DSI"
    return f"""Vbat bat 0 PULSE(0 {p['pol']*p['vbat']} 1m 4m 1 1 2)
{prot}
Rl load 0 {p['rl']}
Cl load 0 10u"""
