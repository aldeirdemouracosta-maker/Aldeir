"""Energia solar: modelo de painel fotovoltaico, carregador MPPT-manual e sombreamento."""

from __future__ import annotations

import math

from .base import Lesson, Param, PI, circuit, dc, tran_time, OP

VT25 = 0.025852


def pv_block(tag, pos, neg, g, temp=25.0, ncell=36, isc_ref=8.0, voc_ref=21.6, rs=0.25, rsh=400.0, ideality=1.3):
    """Emite um painel (modelo de um diodo) como componentes de netlist."""
    n_tot = ideality * ncell
    vt = 1.380649e-23 * (temp + 273.15) / 1.602176634e-19
    iph = max(isc_ref * g / 1000.0 * (1 + 0.0005 * (temp - 25)), 1e-6)
    i_s = isc_ref / (math.exp(voc_ref / (n_tot * VT25)) - 1)
    return (f".model DPV_{tag} D(Is={i_s:.6e} N={n_tot:.4f} Rs=0 Eg=1.12 Xti=3)\n"
            f"Iph_{tag} {neg} pi_{tag} DC {iph:.6g}\n"
            f"Dpv_{tag} pi_{tag} {neg} DPV_{tag}\n"
            f"Rsh_{tag} pi_{tag} {neg} {rsh}\n"
            f"Rs_{tag} pi_{tag} {pos} {rs}")


def pv_stats(g, temp, ncell=36, isc_ref=8.0, voc_ref=21.6, ideality=1.3):
    vt = 1.380649e-23 * (temp + 273.15) / 1.602176634e-19
    n_tot = ideality * ncell
    iph = isc_ref * g / 1000.0 * (1 + 0.0005 * (temp - 25))
    i_s = isc_ref / (math.exp(voc_ref / (n_tot * VT25)) - 1)
    voc = n_tot * vt * math.log(iph / i_s + 1)
    return iph, voc


@circuit(
    id="pv_panel_iv", name="Painel fotovoltaico – curva I-V e P-V", category="solar",
    summary="Modelo de um diodo de painel de 36 células (≈ 130 W). Varre a tensão e mostra corrente e potência.",
    params=[Param("g", "Irradiância", 1000.0, "W/m²", 50, 1200), Param("t", "Temperatura das células", 25.0, "°C", -10, 85)],
    analyses=lambda p: {"Curva I-V": dc("Vld", 0, pv_stats(p["g"], p["t"])[1] * 1.02, 0.1)}, probes=["ipv", "pw"],
    theory=lambda p: {"Isc ≈ Iph": (pv_stats(p["g"], p["t"])[0], "A"), "Voc": (pv_stats(p["g"], p["t"])[1], "V"),
                      "Pmax ≈ 0,75·Voc·Isc": (0.75 * pv_stats(p["g"], p["t"])[0] * pv_stats(p["g"], p["t"])[1], "W")},
    lesson=Lesson(objetivo="Entender a curva característica de um painel solar e o ponto de máxima potência (MPP).",
                  teoria=["A célula é uma fonte de corrente (fótons) em paralelo com um diodo. Corrente ≈ constante até o 'joelho' e depois cai.",
                          "Mais irradiância = mais corrente (proporcional). Mais temperatura = menos tensão (≈ −0,3 %/°C).",
                          "A potência P = V·I tem máximo (MPP) no joelho: é onde o MPPT trabalha."],
                  observe=["Curva 'pw' (potência) com um máximo único.", "Reduza a irradiância a 300 W/m²: Isc cai 70 %, Voc só um pouco."],
                  experimentos=["Eleve a temperatura para 70 °C: a tensão de circuito aberto diminui.", "Meça a tensão do MPP (≈ 80 % de Voc)."]))
def pv_iv(p):
    return (pv_block("a", "pos", "0", p["g"], p["t"]) +
            f"\nVld pos 0 DC 0\n.temp {p['t']}\nBipv ipv 0 V=I(Vld)\nBpw pw 0 V=V(pos)*I(Vld)")


def _charger_theory(p):
    iph, voc = pv_stats(p["g"], 25)
    return {"Voc do painel": (voc, "V"), "Duty ideal p/ MPP (≈ Vbat/Vmpp)": (p["vbat"] / (0.8 * voc), ""),
            "Corrente máxima do painel": (iph, "A")}


@circuit(
    id="solar_buck_charger", name="Carregador solar de bateria (buck, MPPT manual)", category="solar",
    summary="Painel → capacitor → conversor buck → bateria de 12 V. Varie o ciclo de trabalho para achar o ponto de máxima potência.",
    params=[Param("g", "Irradiância", 1000.0, "W/m²", 100, 1200), Param("d", "Ciclo de trabalho D", 0.65, "", 0.2, 0.95),
            Param("vbat", "Tensão da bateria", 12.0, "V", 6, 14.5), Param("l", "Indutor", 100e-6, "H", 1e-6, 1e-2)],
    analyses=lambda p: {"Transient": {"kind": "tran", "step": 0.2e-6, "stop": 4e-3, "maxstep": 0.2e-6, "uic": True}}, probes=["ppv", "pv", "ib"],
    theory=_charger_theory, sweepable=True,
    lesson=Lesson(objetivo="Entender por que painéis solares precisam de MPPT.",
                  teoria=["Em um buck de malha aberta o ponto de operação do painel é imposto por D e pela bateria: se D for muito alto o painel entra no 'cotovelo' e a potência cai.",
                          "O MPPT (perturba-e-observa) ajusta D automaticamente para maximizar V·I do painel."],
                  observe=["Compare a potência do painel 'ppv' para D = 0,5; 0,65 e 0,8."],
                  experimentos=["Use a aba Automação para varrer D e traçar a potência × D.", "Reduza a irradiância (nuvem) e veja o MPP deslocar."],
                  cuidados=["Controladores reais limitam a corrente e a tensão de carga (CC/CV) conforme a química da bateria."]))
def solar_charger(p):
    T = 1 / 100e3
    return (pv_block("a", "pv", "0", p["g"]) + f"""
Vsense pv pvs 0
Cin pvs 0 470u IC=17
Vg g 0 PULSE(0 12 0 5n 5n {p['d']*T:.6e} {T:.6e})
Ssw pvs sw g 0 SWPWR
Dfw 0 sw DSCH
L1 sw lx {p['l']} IC=5
Rl lx out 0.01
Cout out 0 220u IC={p['vbat']}
Rint out vb 0.05
Vbat vb 0 DC {p['vbat']}
Bppv ppv 0 V=V(pv)*I(Vsense)
Bib ib 0 V=(V(out)-V(vb))/0.05""")


@circuit(
    id="solar_shading", name="Sombreamento parcial com diodos de bypass", category="solar",
    summary="Dois sub-conjuntos de 18 células em série; um recebe sombra. O diodo de bypass evita perda total e queima (hot-spot).",
    params=[Param("g1", "Irradiância sub-conjunto 1", 1000.0, "W/m²", 50, 1200), Param("g2", "Irradiância sub-conjunto 2 (sombra)", 250.0, "W/m²", 20, 1200),
            Param("bypass", "Diodos de bypass (1 = sim)", 1, "", 0, 1)],
    analyses=lambda p: {"Curva I-V": dc("Vld", 0, 22, 0.1)}, probes=["ipv", "pw"],
    theory=lambda p: {"Isc sub-conjunto 1": (8.0 * p["g1"] / 1000, "A"), "Isc sub-conjunto 2": (8.0 * p["g2"] / 1000, "A")},
    lesson=Lesson(objetivo="Visualizar o efeito da sombra em painéis e a função dos diodos de bypass.",
                  teoria=["Células em série têm a mesma corrente: a mais sombreada limita o conjunto.",
                          "O diodo de bypass conduz quando o sub-conjunto não consegue gerar a corrente do resto, evitando que ele dissipe potência (hot-spot).",
                          "A curva P-V ganha dois picos: o MPPT precisa de busca global."],
                  observe=["Com bypass = 1: a curva I-V tem dois degraus. Com 0: a corrente despenca para o valor da área sombreada."],
                  experimentos=["Sombra de 50 %: g2 = 500."]))
def shading(p):
    byp = (lambda i, a, b: f"Dby{i} {a} {b} DSCH") if p["bypass"] >= 0.5 else (lambda i, a, b: f"Rby{i} {a} {b} 1e9")
    return (pv_block("a", "m", "0", p["g1"], ncell=18, isc_ref=8.0, voc_ref=10.8, rs=0.12, rsh=200) + "\n" +
            pv_block("b", "pos", "m", p["g2"], ncell=18, isc_ref=8.0, voc_ref=10.8, rs=0.12, rsh=200) + "\n" +
            byp(1, "0", "m") + "\n" + byp(2, "m", "pos") + "\n" +
            "Vld pos 0 DC 0\nBipv ipv 0 V=I(Vld)\nBpw pw 0 V=V(pos)*I(Vld)")
