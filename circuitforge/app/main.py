"""
CircuitForge – EWB 2.0 · Interface Streamlit
Biblioteca de circuitos + simulação ngspice + instrutor e criador mediados por IA LOCAL (sob demanda).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from automation import MonteCarlo, ParameterSweep
from automation.metrics import METRICS, gain_db_at, peak_freq
from core.footprints import SUPPORTED, build_footprint
from core.library import CATEGORIES, REGISTRY, by_category
from core.simulator import CircuitSimulator
from core.spice_engine import SpiceError, ngspice_available, sanitize_netlist
from core.tutor import fmt, lesson_markdown, static_quiz
from core.units import parse_si, to_si
from instruments import BodePlotter, Oscilloscope, RFAnalyzer, SpectrumAnalyzer, visible_channels
from llm import (ElectronicsLLM, LLMUnavailable, MODEL_NOTES, installed_models, ollama_online, recommend_model)
from llm.validation import default_analysis_for, validate_netlist

st.set_page_config(page_title="CircuitForge – EWB 2.0", page_icon="⚡", layout="wide")
S = st.session_state


# ---------------------------------------------------------------------------------------
# Estado e utilidades
# ---------------------------------------------------------------------------------------
def ss(key, default):
    if key not in S:
        S[key] = default
    return S[key]


ss("work", None)          # circuito simulado atual (dict)
ss("ai", {})              # saídas da IA (explicações, quiz, ...)
ss("my_circuits", {})     # circuitos criados/colados pelo usuário
ss("ai_enabled", False)


def si_input(label: str, default: float, unit: str, key: str, lo=None, hi=None, help_text=None) -> float:
    """Campo de texto com notação de engenharia (4.7k, 100n, 1meg)."""
    txt = st.text_input(f"{label} [{unit}]" if unit else label, value=to_si(default), key=key, help=help_text)
    try:
        v = parse_si(txt)
    except ValueError:
        st.caption(f"⚠️ valor inválido, usando {to_si(default)}")
        return default
    if lo is not None and v < lo:
        st.caption(f"⚠️ mínimo {to_si(lo)}; ajustado")
        v = lo
    if hi is not None and v > hi:
        st.caption(f"⚠️ máximo {to_si(hi)}; ajustado")
        v = hi
    return v


def get_llm() -> ElectronicsLLM:
    return ElectronicsLLM(model=S.get("llm_model", "qwen2.5:1.5b"), host=S.get("llm_host", "http://localhost:11434"),
                          temperature=S.get("llm_temp", 0.2))


def ai_button(label: str, key: str, help_text: str = "") -> bool:
    """Todos os botões de IA passam por aqui: só funcionam com a IA habilitada na barra lateral."""
    if not S.ai_enabled:
        st.button(f"🤖 {label}", key=key, disabled=True, help="Ative 'Recursos de IA' na barra lateral.")
        return False
    return st.button(f"🤖 {label}", key=key, help=help_text or "Roda o modelo local (Ollama) somente agora.")


def ai_error(e: Exception):
    st.error(str(e))
    st.caption("Dica: instale o Ollama (https://ollama.com), rode `ollama serve` e `ollama pull qwen2.5:1.5b`.")


def run_simulation(netlist: str, spec: dict, title: str, circuit_id=None, params=None, probes=None, has_title=True):
    sim = CircuitSimulator(title)
    sim.load_netlist(netlist, has_title=has_title)
    res = sim.run(spec)
    S.work = {"title": title, "netlist": sim.netlist, "spec": spec, "result": res, "kind": spec["kind"],
              "circuit_id": circuit_id, "params": params or {}, "probes": probes or [], "warnings": sim.warnings}
    return S.work


def probe_defaults(work, available):
    p = [x for x in work["probes"] if x in available]
    return p or available[:2]


def op_table(res: dict) -> pd.DataFrame:
    rows = [(k, v) for k, v in res.items() if "." not in k and not k.startswith("i(")]
    rows += [(k, v) for k, v in res.items() if k.startswith("i(") and "." not in k]
    return pd.DataFrame([{"Nó / Corrente": k, "Valor": fmt(v, "A" if k.startswith("i(") else "V")} for k, v in rows])


def show_result(work, key_prefix: str, compact: bool = True):
    res, kind = work["result"], work["kind"]
    if kind == "tran":
        chans = visible_channels(res)
        pick = st.multiselect("Canais", chans, default=probe_defaults(work, chans), key=f"{key_prefix}_ch")
        scope = Oscilloscope(work["title"])
        scope.load(res)
        t_end = res["time"][-1]
        unit = "s" if t_end >= 1 else "ms" if t_end >= 1e-3 else "us" if t_end >= 1e-6 else "ns"
        st.plotly_chart(scope.plot(pick, time_unit=unit), width="stretch", key=f"{key_prefix}_plot")
        if pick:
            cols = st.columns(min(len(pick), 4))
            for c, ch in zip(cols, pick[:4]):
                m = scope.measure(ch)
                with c:
                    st.metric(f"{ch} · Vpp", fmt(m["Vpp"], "V"))
                    st.caption(f"média {fmt(m['Vavg'], 'V')} · RMS(AC) {fmt(m['Vrms_AC'], 'V')} · f ≈ {fmt(m['Freq_Hz'], 'Hz')}")
    elif kind == "ac":
        if "gamma_mag" in res:
            rf = RFAnalyzer(work["title"])
            st.plotly_chart(rf.plot(res), width="stretch", key=f"{key_prefix}_rf")
            st.json({k: (fmt(v, "Hz") if "Hz" in k else round(v, 3)) for k, v in rf.summary(res).items()})
        else:
            b = BodePlotter(work["title"])
            b.load(res)
            chans = b.channels()
            pick = st.multiselect("Nós", chans, default=probe_defaults(work, chans)[:2], key=f"{key_prefix}_chb")
            st.plotly_chart(b.plot(pick), width="stretch", key=f"{key_prefix}_bode")
            if pick:
                c = b.find_cutoff(pick[0])
                if c:
                    txt = f"Tipo: **{c['type']}** · pico {c['peak_db']:.1f} dB em {fmt(c['f_peak'], 'Hz')}"
                    if c["f_low"]:
                        txt += f" · f₋₃dB inferior {fmt(c['f_low'], 'Hz')}"
                    if c["f_high"]:
                        txt += f" · f₋₃dB superior {fmt(c['f_high'], 'Hz')}"
                    st.info(txt)
    elif kind == "dc":
        chans = [k for k in res if k != "sweep" and "." not in k]
        pick = st.multiselect("Sinais", chans, default=probe_defaults(work, chans), key=f"{key_prefix}_chd")
        fig = go.Figure()
        for ch in pick:
            fig.add_trace(go.Scatter(x=res["sweep"], y=res[ch], mode="lines", name=ch))
        fig.update_layout(template="plotly_dark", height=450, xaxis_title="Varredura (V)", yaxis_title="Valor")
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_dc")
    else:
        st.dataframe(op_table(res), width="stretch", hide_index=True)


# ---------------------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ CircuitForge")
    st.caption("Electronic Workbench 2.0")
    if ngspice_available():
        st.success("ngspice encontrado", icon="✅")
    else:
        st.error("ngspice não encontrado: `sudo apt install ngspice`")
    st.divider()
    st.subheader("🤖 IA local (opcional)")
    S.ai_enabled = st.toggle("Recursos de IA", value=S.ai_enabled,
                             help="Desligado: biblioteca, lições e simulações funcionam normalmente. Ligado: botões 🤖 ficam ativos.")
    st.caption("A IA **só roda quando você clica em um botão 🤖**. Nada é enviado para a internet: o modelo roda no seu computador (Ollama).")
    if S.ai_enabled:
        S.llm_host = st.text_input("Servidor Ollama", value=S.get("llm_host", os.environ.get("OLLAMA_HOST", "http://localhost:11434")))
        models = installed_models(S.llm_host)
        names = [m["name"] for m in models]
        if names:
            idx = names.index(recommend_model(names)) if recommend_model(names) in names else 0
            S.llm_model = st.selectbox("Modelo instalado", names, index=idx,
                                       format_func=lambda n: f"{n} ({next(m['size_gb'] for m in models if m['name']==n):.1f} GB)")
        else:
            st.warning("Ollama não respondeu ou não há modelos.")
            S.llm_model = st.text_input("Nome do modelo", value=S.get("llm_model", "qwen2.5:1.5b"))
        S.llm_temp = st.slider("Criatividade", 0.0, 1.0, S.get("llm_temp", 0.2), 0.05)
        with st.expander("Modelos leves recomendados"):
            for k, v in MODEL_NOTES.items():
                st.markdown(f"- `{k}` – {v}")
            st.caption("Modelos < 1 GB explicam bem, mas erram mais ao criar circuitos; o Criador valida no ngspice e corrige sozinho.")
    st.divider()
    st.caption(f"{len(REGISTRY)} circuitos · {len(CATEGORIES)} categorias")

st.title("⚡ CircuitForge – Electronic Workbench 2.0")
tab_lib, tab_inst, tab_ai, tab_meter, tab_auto, tab_fp, tab_about = st.tabs([
    "🔌 Biblioteca & Simulação", "🎓 Instrutor", "🛠 Criador (IA)", "🔬 Instrumentos", "🔁 Automação", "📦 Footprints", "ℹ️ Sobre"])

# ---------------------------------------------------------------------------------------
# Aba 1 – Biblioteca & Simulação
# ---------------------------------------------------------------------------------------
with tab_lib:
    cats = by_category()
    c1, c2 = st.columns([1, 2])
    with c1:
        cat = st.selectbox("Categoria", list(CATEGORIES), format_func=lambda k: f"{CATEGORIES[k]} ({len(cats[k])})", key="cat")
    with c2:
        options = cats[cat]
        cdef = st.selectbox("Circuito", options, format_func=lambda c: c.name, key=f"circ_{cat}")
    S.current_id = cdef.id
    st.caption(cdef.summary)

    left, right = st.columns([1, 2.2])
    with left:
        st.markdown("**Parâmetros**")
        params = {}
        for p in cdef.params:
            params[p.key] = si_input(p.label, p.default, p.unit, key=f"p_{cdef.id}_{p.key}", lo=p.min, hi=p.max)
        analyses = cdef.analysis_options(params)
        an_name = st.selectbox("Análise", list(analyses), key=f"an_{cdef.id}")
        spec = analyses[an_name]
        with st.expander("Netlist SPICE (editável)"):
            net_default = cdef.netlist(params)
            net_text = st.text_area("Netlist", value=net_default, height=260, key=f"net_{cdef.id}_{hash(net_default) % 10**8}")
            use_edit = st.checkbox("Simular o netlist editado", value=False, key=f"useedit_{cdef.id}")
            st.download_button("⬇️ Baixar .cir", net_text, file_name=f"{cdef.id}.cir")
        run_btn = st.button("▶ Simular", type="primary", width="stretch", key=f"run_{cdef.id}")

    with right:
        if run_btn:
            try:
                with st.spinner("Simulando com ngspice..."):
                    run_simulation(net_text if use_edit else net_default, spec, cdef.name, cdef.id, params, cdef.probes)
            except (SpiceError, ValueError) as e:
                st.error(f"Erro na simulação: {e}")
        w = S.work
        if w and w["circuit_id"] == cdef.id:
            for msg in w.get("warnings", []):
                st.caption(f"ℹ️ {msg}")
            show_result(w, "lib")
            theory = cdef.theory_values(w["params"])
            if theory:
                st.markdown("**🧮 Valores teóricos**")
                st.dataframe(pd.DataFrame([{"Grandeza": k, "Valor": fmt(v[0], v[1])} for k, v in theory.items()]),
                             hide_index=True, width="stretch")
        else:
            st.info("Ajuste os parâmetros e clique em **▶ Simular**. Os resultados também ficam disponíveis nas abas Instrutor, Instrumentos e Automação.")

# ---------------------------------------------------------------------------------------
# Aba 2 – Instrutor
# ---------------------------------------------------------------------------------------
with tab_inst:
    w = S.work
    cid = (w or {}).get("circuit_id") or S.get("current_id")
    ic = REGISTRY.get(cid)
    if not ic:
        st.info("Escolha um circuito da biblioteca na primeira aba.")
    else:
        iparams = (w["params"] if w and w["circuit_id"] == cid else ic.defaults())
        st.caption("O modo Instrutor funciona **sem IA** (lição, fórmulas e quiz). Os botões 🤖 pedem ao modelo local uma explicação personalizada com os seus números.")
        col_l, col_r = st.columns([1.3, 1])
        with col_l:
            st.markdown(lesson_markdown(ic, iparams))
        with col_r:
            st.markdown("#### 📝 Quiz rápido (sem IA)")
            seed = ss(f"qseed_{cid}", 0)
            quiz = static_quiz(ic, iparams, n=3, seed=seed)
            if not quiz:
                st.caption("Este circuito ainda não tem fórmulas suficientes para quiz automático.")
            for qi, q in enumerate(quiz):
                ans = st.radio(q["pergunta"], q["opcoes"], index=None, key=f"q_{cid}_{seed}_{qi}")
                if ans is not None:
                    ok = q["opcoes"].index(ans) == q["correta"]
                    (st.success if ok else st.error)(("✅ Correto! " if ok else "❌ Não foi dessa vez. ") + q["explicacao"])
            if quiz and st.button("🔄 Novas perguntas", key=f"newq_{cid}"):
                S[f"qseed_{cid}"] = seed + 1
                st.rerun()

        st.divider()
        st.markdown("#### 🤖 Instrutor com IA local")
        measured = {}
        if w and w["circuit_id"] == cid and w["kind"] == "tran" and ic.probes:
            sc = Oscilloscope()
            sc.load(w["result"])
            ch = next((p for p in ic.probes if p in w["result"]), None)
            if ch:
                measured = {f"{ch}.{k}": v for k, v in sc.measure(ch).items() if k in ("Vpp", "Vavg", "Vrms_AC", "Freq_Hz")}
        level = st.radio("Nível", ["iniciante", "intermediário", "avançado"], horizontal=True, key=f"lvl_{cid}")
        b1, b2, b3 = st.columns(3)
        akey = f"{cid}"
        with b1:
            if ai_button("Explicar este circuito", f"ai_exp_{cid}"):
                try:
                    with st.spinner("O instrutor está pensando..."):
                        S.ai.setdefault("exp", {})[akey] = get_llm().explain_circuit(ic, iparams, ic.theory_values(iparams), measured, level)
                except LLMUnavailable as e:
                    ai_error(e)
        with b2:
            if ai_button("Gerar quiz com IA", f"ai_quiz_{cid}"):
                try:
                    with st.spinner("Criando perguntas..."):
                        S.ai.setdefault("quiz", {})[akey] = get_llm().quiz(ic, iparams, n=3)
                except (LLMUnavailable, ValueError) as e:
                    ai_error(e)
        with b3:
            if ai_button("Interpretar a forma de onda", f"ai_wave_{cid}") and measured:
                try:
                    with st.spinner("Analisando..."):
                        S.ai.setdefault("wave", {})[akey] = get_llm().explain_waveform({k.split('.')[1]: v for k, v in measured.items()}, ch, ic.name)
                except LLMUnavailable as e:
                    ai_error(e)
        if S.ai.get("exp", {}).get(akey):
            st.markdown(S.ai["exp"][akey])
        if S.ai.get("wave", {}).get(akey):
            st.info(S.ai["wave"][akey])
        for qi, q in enumerate(S.ai.get("quiz", {}).get(akey, [])):
            ans = st.radio(f"IA · {q.pergunta}", q.opcoes, index=None, key=f"aiq_{cid}_{qi}")
            if ans is not None:
                ok = q.opcoes.index(ans) == q.correta
                (st.success if ok else st.error)(("✅ " if ok else "❌ ") + q.explicacao)
        st.markdown("**Pergunte ao instrutor**")
        question = st.text_input("Sua dúvida sobre este circuito", key=f"ask_{cid}")
        if ai_button("Perguntar", f"ai_ask_{cid}") and question.strip():
            try:
                with st.spinner("Pensando..."):
                    S.ai.setdefault("ans", {})[akey] = get_llm().answer(question, ic, iparams)
            except LLMUnavailable as e:
                ai_error(e)
        if S.ai.get("ans", {}).get(akey):
            st.markdown(S.ai["ans"][akey])

# ---------------------------------------------------------------------------------------
# Aba 3 – Criador (IA)
# ---------------------------------------------------------------------------------------
with tab_ai:
    st.subheader("🛠 Criador de circuitos")
    st.caption("Descreva o circuito. A IA local escreve o netlist, o ngspice **valida e simula**, e se houver erro ele é devolvido ao modelo para corrigir (até 3 tentativas).")
    examples = ["Pedal fuzz de guitarra com dois transistores alimentado por 9 V",
                "Fonte de 5 V a partir de 12 V usando regulador série com zener e transistor",
                "Amplificador de áudio com amp-op e ganho 20 para microfone",
                "Filtro passa-faixa de rádio AM em 1 MHz",
                "Carregador de celular para carro com buck 12 V para 5 V",
                "Retificador de meia onda com filtro capacitivo"]
    ex = st.selectbox("Exemplos", ["(escreva o seu abaixo)"] + examples, key="ex_pick")
    request = st.text_area("O que você quer criar?", value="" if ex.startswith("(") else ex, height=90, key=f"req_{ex}")
    attempts = st.slider("Tentativas máximas", 1, 5, 3, key="max_att")
    if ai_button("Criar circuito com IA", "ai_create") and request.strip():
        log_box = st.status("Criando...", expanded=True)
        try:
            def on_attempt(i, raw):
                log_box.write(f"Tentativa {i} recebida – validando no ngspice...")
            created = get_llm().create_circuit(request, max_attempts=attempts, on_attempt=on_attempt)
            S.ai["created"] = created
            log_box.update(label="Pronto" if created.ok else "A IA não conseguiu validar", state="complete" if created.ok else "error")
        except LLMUnavailable as e:
            log_box.update(label="IA indisponível", state="error")
            ai_error(e)
    cr = S.ai.get("created")
    if cr:
        for line in cr.log:
            st.caption(f"• {line}")
        if cr.ok:
            st.success(f"**{cr.title}** – {cr.explanation}")
            res = cr.validation.result
            work = {"title": cr.title, "netlist": cr.netlist, "spec": cr.analysis, "result": res, "kind": cr.analysis["kind"],
                    "circuit_id": None, "params": {}, "probes": cr.probes, "warnings": []}
            show_result(work, "ai")
            st.code(cr.netlist, language="text")
            b1, b2, b3 = st.columns(3)
            with b1:
                st.download_button("⬇️ Baixar .cir", cr.netlist, file_name="circuito_ia.cir")
            with b2:
                if st.button("📌 Usar em Instrumentos/Automação", key="use_ai"):
                    S.work = work
                    st.toast("Circuito enviado para a aba Instrumentos")
            with b3:
                if st.button("💾 Salvar em 'Meus circuitos'", key="save_ai"):
                    S.my_circuits[cr.title] = cr.netlist
                    st.toast("Salvo")
        else:
            st.warning(cr.explanation)
            if cr.netlist:
                with st.expander("Último netlist tentado"):
                    st.code(cr.netlist, language="text")
            if cr.fallback:
                st.info(f"Sugestão da biblioteca: **{REGISTRY[cr.fallback].name}** (categoria {CATEGORIES[REGISTRY[cr.fallback].category]}).")

    st.divider()
    with st.expander("✍️ Escrever/colar um netlist manualmente (sem IA)"):
        manual = st.text_area("Netlist SPICE", height=200, key="manual_net",
                              value="Divisor de tensão\nV1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k\n")
        if st.button("Validar e simular", key="manual_run"):
            v = validate_netlist(manual)
            if v.ok:
                S.work = {"title": "Netlist manual", "netlist": manual, "spec": v.analysis, "result": v.result,
                          "kind": v.analysis["kind"], "circuit_id": None, "params": {}, "probes": v.nodes[:3], "warnings": v.warnings}
                show_result(S.work, "man")
            else:
                st.error(v.message)
        if ai_button("Analisar este netlist (explicar)", "ai_read"):
            try:
                with st.spinner("Lendo o circuito..."):
                    st.markdown(get_llm().read_circuit(manual))
            except LLMUnavailable as e:
                ai_error(e)
    if S.my_circuits:
        with st.expander(f"💾 Meus circuitos ({len(S.my_circuits)})"):
            for name, net in S.my_circuits.items():
                st.markdown(f"**{name}**")
                st.code(net, language="text")

# ---------------------------------------------------------------------------------------
# Aba 4 – Instrumentos
# ---------------------------------------------------------------------------------------
with tab_meter:
    w = S.work
    if not w:
        st.warning("Rode uma simulação primeiro.")
    else:
        st.caption(f"Resultado atual: **{w['title']}** ({w['kind']})")
        show_result(w, "inst")
        res = w["result"]
        if w["kind"] == "tran":
            chans = visible_channels(res)
            st.markdown("#### Analisador de espectro e THD")
            ch = st.selectbox("Canal", chans, index=chans.index(w["probes"][-1]) if w["probes"] and w["probes"][-1] in chans else 0, key="spec_ch")
            sp = SpectrumAnalyzer(w["title"])
            sp.load(res)
            fmax = st.text_input("Frequência máxima do gráfico (vazio = automática)", "", key="spec_fmax")
            try:
                fm = parse_si(fmax) if fmax.strip() else None
            except ValueError:
                fm = None
            st.plotly_chart(sp.plot(ch, fmax=fm), width="stretch", key="spec_plot")
            sc = Oscilloscope()
            sc.load(res)
            t = sc.thd(ch)
            if t and not np.isnan(t.get("THD_percent", np.nan)):
                st.metric("THD (distorção harmônica total)", f"{t['THD_percent']:.3f} %", help=f"fundamental ≈ {fmt(t['f0'], 'Hz')}")
            st.download_button("⬇️ CSV dos canais", pd.DataFrame({k: v for k, v in res.items() if isinstance(v, np.ndarray) and v.ndim == 1 and "." not in k}).to_csv(index=False),
                               file_name="simulacao.csv")
        elif w["kind"] == "op":
            st.download_button("⬇️ CSV", op_table(res).to_csv(index=False), file_name="op.csv")
        with st.expander("Netlist usado"):
            st.code(w["netlist"], language="text")

# ---------------------------------------------------------------------------------------
# Aba 5 – Automação
# ---------------------------------------------------------------------------------------
with tab_auto:
    st.subheader("🔁 Varredura de parâmetros e Monte Carlo")
    w = S.work
    acid = (w or {}).get("circuit_id") or S.get("current_id")
    acd = REGISTRY.get(acid)
    if not acd:
        st.info("Selecione um circuito da biblioteca (aba 1).")
    else:
        base = w["params"] if (w and w["circuit_id"] == acid) else acd.defaults()
        st.markdown(f"Circuito: **{acd.name}**")
        an_opts = list(acd.analysis_options(base))
        aa = st.selectbox("Análise a usar", an_opts, key=f"aa_{acid}")
        spec_a = acd.analysis_options(base)[aa]
        kind = spec_a["kind"]
        probe_default = acd.probes[0] if acd.probes else ""
        node = st.text_input("Nó a medir", probe_default, key=f"node_{acid}")
        if kind == "ac":
            mtype = st.selectbox("Métrica", ["Frequência do pico", "Ganho em frequência fixa (dB)"], key=f"mt_{acid}")
            fx = st.text_input("Frequência do ganho", "1k", key=f"fx_{acid}") if "Ganho" in mtype else None
            def make_metric():
                return peak_freq(node) if "pico" in mtype else gain_db_at(node, parse_si(fx))
        elif kind in ("tran", "dc"):
            mname = st.selectbox("Métrica", list(METRICS), key=f"mt_{acid}")
            def make_metric():
                return METRICS[mname](node)
        else:
            def make_metric():
                return lambda r: {f"V({node})": r[node]}
        t_sw, t_mc = st.tabs(["Varredura", "Monte Carlo"])
        with t_sw:
            pk = st.selectbox("Parâmetro", acd.params, format_func=lambda p: f"{p.label} [{p.unit}]", key=f"swp_{acid}")
            cA, cB, cC = st.columns(3)
            with cA:
                v0 = si_input("Início", pk.default * 0.5, "", f"sw0_{acid}_{pk.key}")
            with cB:
                v1 = si_input("Fim", pk.default * 1.5, "", f"sw1_{acid}_{pk.key}")
            with cC:
                npts = st.slider("Pontos", 3, 40, 9, key=f"swn_{acid}")
            logsp = st.checkbox("Escala logarítmica", key=f"swl_{acid}")
            if st.button("▶ Rodar varredura", key=f"swgo_{acid}"):
                vals = np.geomspace(max(v0, 1e-15), max(v1, 1e-15), npts) if logsp else np.linspace(v0, v1, npts)
                bar = st.progress(0.0)
                try:
                    df = ParameterSweep(acd, base).run(pk.key, list(vals), analysis=aa, measure_fn=make_metric(),
                                                       progress=lambda i, n: bar.progress(i / n))
                    bar.empty()
                    S.sweep_df = df
                except (KeyError, SpiceError) as e:
                    st.error(str(e))
            df = S.get("sweep_df")
            if df is not None and pk.key in df.columns:
                st.dataframe(df, width="stretch", hide_index=True)
                ycol = [c for c in df.columns if c not in (pk.key, "erro")]
                if ycol:
                    fig = go.Figure(go.Scatter(x=df[pk.key], y=df[ycol[0]], mode="lines+markers"))
                    fig.update_layout(template="plotly_dark", height=380, xaxis_title=f"{pk.label} [{pk.unit}]", yaxis_title=ycol[0],
                                      xaxis_type="log" if logsp else "linear")
                    st.plotly_chart(fig, width="stretch", key="sweep_fig")
        with t_mc:
            st.caption("Tolerâncias em %, distribuição normal (3σ = tolerância).")
            tol = {}
            cols = st.columns(3)
            for i, p in enumerate(acd.params[:6]):
                with cols[i % 3]:
                    on = st.checkbox(p.label, value=(i < 2), key=f"mcon_{acid}_{p.key}")
                    t = st.number_input("±%", 0.0, 50.0, 5.0, 0.5, key=f"mct_{acid}_{p.key}", disabled=not on)
                    if on:
                        tol[p.key] = t / 100
            nruns = st.slider("Execuções", 5, 150, 30, key=f"mcn_{acid}")
            if st.button("▶ Rodar Monte Carlo", key=f"mcgo_{acid}"):
                bar = st.progress(0.0)
                try:
                    S.mc_df = MonteCarlo(acd, base).run(tol, nruns, analysis=aa, measure_fn=make_metric(),
                                                         progress=lambda i, n: bar.progress(i / n))
                    bar.empty()
                except (KeyError, SpiceError) as e:
                    st.error(str(e))
            mdf = S.get("mc_df")
            if mdf is not None:
                mcols = [c for c in mdf.columns if c not in ("run", "erro") and c not in acd.defaults()]
                if mcols:
                    st.dataframe(mdf[mcols].describe(), width="stretch")
                    fig = go.Figure(go.Histogram(x=mdf[mcols[0]], nbinsx=20))
                    fig.update_layout(template="plotly_dark", height=350, xaxis_title=mcols[0], yaxis_title="ocorrências")
                    st.plotly_chart(fig, width="stretch", key="mc_fig")

# ---------------------------------------------------------------------------------------
# Aba 6 – Footprints
# ---------------------------------------------------------------------------------------
with tab_fp:
    st.subheader("📦 Pacotes e footprints (KiCad)")
    st.caption("A geometria vem de um gerador determinístico (IPC-7351 nominal). A IA, se ativada, só acrescenta notas de uso.")
    st.caption("Suportados: " + " · ".join(SUPPORTED))
    pk_req = st.text_input("Pacote", "SOIC-8", key="fp_req")
    try:
        fp = build_footprint(pk_req)
    except ValueError as e:
        fp = None
        st.error(str(e))
    if fp:
        a, b = st.columns([1, 1])
        with a:
            st.json({"nome": fp.name, "tipo": fp.package_type, "pinos": fp.pins, "passo_mm": fp.pitch_mm,
                     "corpo_mm": f"{fp.body_mm[0]}×{fp.body_mm[1]}", "descrição": fp.description})
            st.download_button("⬇️ Baixar .kicad_mod", fp.to_kicad(), file_name=f"{fp.name}.kicad_mod")
            if ai_button("Descrever com IA (notas de uso)", "ai_fp"):
                try:
                    with st.spinner("Escrevendo notas..."):
                        S.ai["fp"] = get_llm().create_package(pk_req, describe=True).notes
                except (LLMUnavailable, ValueError) as e:
                    ai_error(e)
            if S.ai.get("fp"):
                st.info(S.ai["fp"])
        with b:
            fig = go.Figure()
            cw, ch_ = fp.courtyard
            fig.add_shape(type="rect", x0=-cw / 2, y0=-ch_ / 2, x1=cw / 2, y1=ch_ / 2, line=dict(color="#888", dash="dot"))
            bw, bh = fp.body_mm
            fig.add_shape(type="rect", x0=-bw / 2, y0=-bh / 2, x1=bw / 2, y1=bh / 2, line=dict(color="#4ECDC4"))
            for p in fp.pads:
                fig.add_shape(type="circle" if p.shape == "circle" else "rect", x0=p.x - p.w / 2, y0=p.y - p.h / 2,
                              x1=p.x + p.w / 2, y1=p.y + p.h / 2, fillcolor="#FF6B6B" if p.number == "1" else "#C44DFF",
                              line=dict(width=0), opacity=0.8)
                fig.add_annotation(x=p.x, y=p.y, text=p.number, showarrow=False, font=dict(size=9, color="white"))
            fig.update_yaxes(scaleanchor="x", autorange="reversed", visible=False)
            fig.update_xaxes(visible=False)
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="fp_fig")
        with st.expander("Arquivo .kicad_mod"):
            st.code(fp.to_kicad(), language="lisp")

# ---------------------------------------------------------------------------------------
# Aba 7 – Sobre
# ---------------------------------------------------------------------------------------
with tab_about:
    st.markdown(f"""
**CircuitForge – EWB 2.0** é um laboratório de eletrônica open-source com **{len(REGISTRY)} circuitos prontos** em
{len(CATEGORIES)} áreas: fundamentos, fontes, placas de computador, IA, amplificadores de som, pedais de guitarra,
energia solar, circuitos veiculares, rádio/TV e antenas.

* **Simulação:** ngspice em modo batch (DC, AC, transiente, ponto de operação) – sem depender do PySpice.
* **Instrutor:** lição, fórmulas, quiz e comparação teoria × simulação – funcionam **sem IA**.
* **IA local (sob demanda):** explicações, quiz, perguntas e **criação de circuitos** validados no ngspice. Só roda ao clicar nos botões 🤖.
* **Segurança:** netlists (inclusive da IA) são sanitizados: sem `.control`, `.include` ou acesso a arquivos.
* **Limites:** os modelos são comportamentais/didáticos (amp-op de 1 polo, chaves ideais). Não substituem simulação com modelos de fabricante nem validação em bancada.
""")
    cats = by_category()
    for k, lst in cats.items():
        with st.expander(f"{CATEGORIES[k]} – {len(lst)} circuitos"):
            for c in lst:
                st.markdown(f"- **{c.name}** – {c.summary}")
