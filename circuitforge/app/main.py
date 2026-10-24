"""
CircuitForge – EWB 2.0
Interface principal Streamlit
"""

from __future__ import annotations
import sys
from pathlib import Path

# Garante que o pacote raiz está no path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import numpy as np
import pandas as pd
from typing import Optional

from core.simulator import CircuitSimulator
from core.netlist import (
    build_rc_lowpass,
    build_rc_highpass,
    build_rc_integrator,
    build_rc_differentiator,
    build_voltage_divider,
    build_series_rlc,
    build_halfwave_rectifier,
    build_fullwave_bridge,
    build_inverting_opamp,
    build_noninverting_opamp,
    build_common_emitter,
    build_astable_555,
    list_example_circuits,
    get_builder,
)
from core.modifier import (
    list_modification_presets,
    apply_preset,
)
from instruments.scope import Oscilloscope
from instruments.bode import BodePlotter
from llm.electronics_llm import ElectronicsLLM, list_light_models, recommend_model
import base64
import tempfile
import os

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CircuitForge – EWB 2.0",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ CircuitForge – Electronic Workbench 2.0")
st.caption("Simulação SPICE + Instrumentos Virtuais + LLM local leve para pacotes e leitura de circuitos")

# ---------------------------------------------------------------------------
# Sidebar – Configuração global
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuração")

    st.subheader("LLM Local (leve < 1 GB)")
    available_llms = list_light_models()
    default_model = recommend_model()
    if available_llms:
        llm_model = st.selectbox(
            "Modelo Ollama",
            options=available_llms,
            index=0 if default_model not in available_llms else available_llms.index(default_model),
        )
        st.success(f"{len(available_llms)} modelo(s) detectado(s)")
    else:
        llm_model = st.text_input("Modelo Ollama", value=default_model)
        st.warning("Ollama não detectado. Rode `ollama serve` e `ollama pull qwen2:0.5b`")

    llm_temp = st.slider("Temperature LLM", 0.0, 1.0, 0.25, 0.05)

    st.divider()
    st.markdown("**Modelos recomendados (< 1 GB)**")
    st.code("qwen2:0.5b   (~350 MB)\ntinyllama    (~637 MB)\nllama3.2:1b  (~1.3 GB)")

# ---------------------------------------------------------------------------
# Abas principais
# ---------------------------------------------------------------------------
tab_sim, tab_instr, tab_auto, tab_llm, tab_mod, tab_about = st.tabs([
    "🔌 Simulação",
    "📟 Instrumentos",
    "📊 Automação",
    "🤖 LLM Eletrônica",
    "🔧 Modificar / Foto",
    "ℹ️ Sobre",
])

# ====================== ABA 1 – SIMULAÇÃO ======================
with tab_sim:
    st.subheader("Simulação SPICE")

    col_cfg, col_run = st.columns([1, 2])

    with col_cfg:
        example = st.selectbox(
            "Circuito de exemplo",
            options=list(list_example_circuits().keys()),
            format_func=lambda k: f"{k} – {list_example_circuits()[k]}",
        )

        # Parâmetros dinâmicos conforme o circuito escolhido
        params = {}
        if example in ("rc_lowpass", "rc_highpass", "rc_integrator", "rc_differentiator"):
            params["r_value"] = st.number_input("R (Ω)", value=1000.0, step=100.0, key=f"r_{example}")
            params["c_value"] = st.number_input("C (F)", value=100e-9, format="%.2e", key=f"c_{example}")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=1.0, key=f"amp_{example}")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=1000.0, key=f"freq_{example}")
        elif example == "voltage_divider":
            params["r1"] = st.number_input("R1 (Ω)", value=10000.0, key="r1_div")
            params["r2"] = st.number_input("R2 (Ω)", value=10000.0, key="r2_div")
            params["vin"] = st.number_input("Vin (V)", value=5.0, key="vin_div")
        elif example == "series_rlc":
            params["r_value"] = st.number_input("R (Ω)", value=50.0, key="r_rlc")
            params["l_value"] = st.number_input("L (H)", value=10e-3, format="%.2e", key="l_rlc")
            params["c_value"] = st.number_input("C (F)", value=100e-9, format="%.2e", key="c_rlc")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=1.0, key="amp_rlc")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=5000.0, key="freq_rlc")
        elif example in ("halfwave_rectifier", "fullwave_bridge"):
            params["r_load"] = st.number_input("R carga (Ω)", value=1000.0, key=f"rl_{example}")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=10.0, key=f"amp_{example}")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=60.0, key=f"freq_{example}")
        elif example == "inverting_opamp":
            params["r_in"] = st.number_input("Rin (Ω)", value=10000.0, key="rin_inv")
            params["r_f"] = st.number_input("Rf (Ω)", value=100000.0, key="rf_inv")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=0.1, key="amp_inv")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=1000.0, key="freq_inv")
        elif example == "noninverting_opamp":
            params["r1"] = st.number_input("R1 (Ω)", value=10000.0, key="r1_ni")
            params["r2"] = st.number_input("R2 (Ω)", value=90000.0, key="r2_ni")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=0.1, key="amp_ni")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=1000.0, key="freq_ni")
        elif example == "common_emitter":
            params["rb"] = st.number_input("Rb (Ω)", value=100000.0, key="rb_ce")
            params["rc"] = st.number_input("Rc (Ω)", value=2000.0, key="rc_ce")
            params["re"] = st.number_input("Re (Ω)", value=200.0, key="re_ce")
            params["vcc"] = st.number_input("Vcc (V)", value=12.0, key="vcc_ce")
            params["vin_amplitude"] = st.number_input("Amplitude Vin (V)", value=0.01, key="amp_ce")
            params["vin_freq"] = st.number_input("Frequência Vin (Hz)", value=1000.0, key="freq_ce")
        elif example == "astable_555":
            params["r_a"] = st.number_input("Ra (Ω)", value=10000.0, key="ra_555")
            params["r_b"] = st.number_input("Rb (Ω)", value=10000.0, key="rb_555")
            params["c"] = st.number_input("C (F)", value=100e-9, format="%.2e", key="c_555")
            st.info("Modelo comportamental do 555: f ≈ 1,44 / ((Ra + 2·Rb)·C).")

        analysis = st.radio(
            "Tipo de análise",
            ["Transient", "AC (Bode)", "Operating Point"],
            horizontal=True,
        )

        if analysis == "Transient":
            step = st.number_input("Step time (s)", value=1e-6, format="%.1e")
            end = st.number_input("End time (s)", value=5e-3, format="%.1e")
        elif analysis == "AC (Bode)":
            f_start = st.number_input("Freq início (Hz)", value=1.0)
            f_stop = st.number_input("Freq fim (Hz)", value=1e6, format="%.1e")
            ppd = st.number_input("Pontos/década", value=20)

        run_btn = st.button("▶ Rodar Simulação", type="primary", width="stretch")

    with col_run:
        if run_btn:
            try:
                sim = CircuitSimulator(title=f"CircuitForge – {example}")
                builder = get_builder(example)
                if builder is None:
                    st.error(f"Construtor não encontrado para: {example}")
                else:
                    circuit = builder(**params)
                    sim.circuit = circuit

                    with st.spinner("Simulando com ngspice..."):
                        if analysis == "Transient":
                            result = sim.run_transient(step_time=step, end_time=end)
                            st.session_state["last_result"] = result
                            st.session_state["last_type"] = "transient"
                            st.session_state["last_circuit"] = example
                            st.success("Simulação transient concluída!")
                        elif analysis == "AC (Bode)":
                            result = sim.run_ac(start_freq=f_start, stop_freq=f_stop, points_per_decade=ppd)
                            st.session_state["last_result"] = result
                            st.session_state["last_type"] = "ac"
                            st.session_state["last_circuit"] = example
                            st.success("Análise AC concluída!")
                        else:
                            result = sim.run_operating_point()
                            st.session_state["last_result"] = result
                            st.session_state["last_type"] = "op"
                            st.session_state["last_circuit"] = example
                            st.success("Ponto de operação calculado!")
                            st.json(result)

            except Exception as e:
                st.error(f"Erro na simulação: {e}")
                st.info(
                    "Verifique se o ngspice está instalado (`sudo apt install ngspice`) "
                    "e que o PySpice está instalado (usado para montar os circuitos)."
                )

        # Exibe último resultado se existir
        if "last_result" in st.session_state and st.session_state.get("last_type") != "op":
            st.markdown("#### Resultado da última simulação")
            res = st.session_state["last_result"]
            if st.session_state["last_type"] == "transient":
                scope = Oscilloscope()
                scope.load(res)
                fig = scope.plot()
                st.plotly_chart(fig, width="stretch")

                # Medições
                chs = [k for k in res.keys() if k != "time"]
                if chs:
                    meas = scope.measure(chs[0])
                    st.write("**Medições automáticas**")
                    st.json(meas)
            else:
                bode = BodePlotter()
                bode.load(res)
                fig = bode.plot()
                st.plotly_chart(fig, width="stretch")

# ====================== ABA 2 – INSTRUMENTOS ======================
with tab_instr:
    st.subheader("Instrumentos Virtuais")
    st.info("Os instrumentos usam o resultado da última simulação da aba **Simulação**.")

    if "last_result" not in st.session_state:
        st.warning("Rode uma simulação primeiro.")
    else:
        res = st.session_state["last_result"]
        rtype = st.session_state.get("last_type", "")

        if rtype == "transient":
            scope = Oscilloscope("Osciloscópio – CircuitForge")
            scope.load(res)
            channels = [k for k in res.keys() if k != "time"]
            selected = st.multiselect("Canais", channels, default=channels[:2])
            fig = scope.plot(channels=selected)
            st.plotly_chart(fig, width="stretch")

            if selected:
                st.markdown("#### Medições")
                cols = st.columns(len(selected))
                for i, ch in enumerate(selected):
                    with cols[i]:
                        m = scope.measure(ch)
                        st.metric(f"{ch} Vpp", f"{m.get('Vpp', 0):.3f} V")
                        st.caption(f"Freq ≈ {m.get('Freq_Hz', 0):.1f} Hz")
        elif rtype == "ac":
            bode = BodePlotter("Bode – CircuitForge")
            bode.load(res)
            channels = list(bode.mag.keys())
            selected = st.multiselect("Nós", channels, default=channels[:1])
            fig = bode.plot(channels=selected)
            st.plotly_chart(fig, width="stretch")
            if selected:
                fc = bode.find_cutoff(selected[0])
                if fc:
                    st.metric("Frequência de corte (-3 dB)", f"{fc:.1f} Hz")
        else:
            st.json(res)

# ====================== ABA 3 – AUTOMAÇÃO ======================
with tab_auto:
    st.subheader("Automação – Varredura e Monte Carlo")
    st.markdown(
        "Ainda em construção no MVP. "
        "Os módulos `ParameterSweep` e `MonteCarlo` já estão implementados em "
        "`automation/` e podem ser usados via código Python."
    )

    st.code("""
from automation.sweep import ParameterSweep
from automation.montecarlo import MonteCarlo

# Exemplo de uso (factory que reconstrói o circuito com novos valores)
def factory(r):
    sim = CircuitSimulator()
    sim.circuit = build_rc_lowpass(r_value=r, c_value=100e-9)
    return sim

sweep = ParameterSweep(factory)
# df = sweep.sweep_transient("R", [500, 1000, 2000, 5000])
""", language="python")

# ====================== ABA 4 – LLM ELETRÔNICA ======================
with tab_llm:
    st.subheader("🤖 LLM Local – Pacotes & Leitura de Circuitos")
    st.caption(f"Modelo ativo: **{llm_model}** (leve, roda 100% local)")

    llm_mode = st.radio(
        "Tarefa",
        [
            "Criar pacote / footprint",
            "Ler / descrever circuito",
            "Gerar netlist SPICE",
            "Explicar forma de onda",
        ],
        horizontal=True,
    )

    interpreter = ElectronicsLLM(model=llm_model, temperature=llm_temp)

    if llm_mode == "Criar pacote / footprint":
        st.markdown("#### Criação de pacote eletrônico")
        col1, col2 = st.columns(2)
        with col1:
            comp_name = st.text_input("Nome do componente", value="LM358")
            pkg_hint = st.text_input("Dica de encapsulamento", value="SOIC-8")
        with col2:
            pins = st.number_input("Número de pinos", min_value=0, value=8)
            extra = st.text_input("Informações extras", value="")

        if st.button("📦 Gerar pacote", type="primary"):
            with st.spinner(f"Gerando com {llm_model}..."):
                try:
                    pkg = interpreter.create_package(
                        component_name=comp_name,
                        package_hint=pkg_hint,
                        pins=int(pins) if pins else None,
                        extra=extra,
                    )
                    st.success("Pacote gerado!")
                    st.json(pkg.to_dict())
                    if pkg.footprint_kicad:
                        st.code(pkg.footprint_kicad, language="lisp")
                except Exception as e:
                    st.error(f"Erro: {e}")
                    st.info("Verifique se o Ollama está rodando e o modelo está baixado.")

    elif llm_mode == "Ler / descrever circuito":
        st.markdown("#### Leitura de circuito / netlist")
        desc = st.text_area(
            "Cole a descrição, netlist ou texto do esquemático",
            value="""R1 1 2 1k
C1 2 0 100n
Vin 1 0 SIN(0 1 1k)
.tran 1u 5m
.end""",
            height=180,
        )
        ctx = st.text_input("Contexto adicional (opcional)", value="")

        if st.button("🔍 Analisar circuito", type="primary"):
            with st.spinner(f"Analisando com {llm_model}..."):
                try:
                    reading = interpreter.read_circuit(desc, context=ctx)
                    st.success("Análise concluída!")
                    st.markdown(f"**Resumo:** {reading.summary}")
                    st.markdown(f"**Topologia:** {reading.topology}")
                    st.markdown(f"**Função:** {reading.function}")
                    st.write("**Componentes detectados:**", reading.components)
                    st.write("**Sugestões:**", reading.suggestions)
                    if reading.netlist_hint:
                        st.code(reading.netlist_hint, language="spice")
                    with st.expander("JSON completo"):
                        st.json(reading.to_dict())
                except Exception as e:
                    st.error(f"Erro: {e}")

    elif llm_mode == "Gerar netlist SPICE":
        st.markdown("#### Geração de netlist a partir de linguagem natural")
        nat = st.text_area(
            "Descreva o circuito",
            value="Filtro RC passa-baixa com resistor de 1 kΩ e capacitor de 100 nF, "
                  "excitado por uma fonte senoidal de 1 V e 1 kHz.",
            height=120,
        )
        atype = st.selectbox("Tipo de análise", ["transient", "ac", "op"])

        if st.button("📝 Gerar netlist", type="primary"):
            with st.spinner("Gerando netlist..."):
                try:
                    net = interpreter.generate_netlist(nat, analysis_type=atype)
                    st.code(net, language="spice")
                except Exception as e:
                    st.error(f"Erro: {e}")

    else:  # Explicar forma de onda
        st.markdown("#### Explicação de medições / forma de onda")
        circ_desc = st.text_input(
            "Descrição do circuito",
            value="Filtro RC passa-baixa 1kΩ + 100nF",
        )
        st.write("Medições (preencha ou use da última simulação):")
        c1, c2, c3 = st.columns(3)
        with c1:
            vpp = st.number_input("Vpp", value=0.7)
        with c2:
            freq_m = st.number_input("Freq (Hz)", value=1000.0)
        with c3:
            vrms = st.number_input("Vrms", value=0.25)

        if st.button("💡 Explicar", type="primary"):
            with st.spinner("Interpretando..."):
                try:
                    explanation = interpreter.explain_waveform(
                        circ_desc,
                        {"Vpp": vpp, "Freq_Hz": freq_m, "Vrms": vrms},
                    )
                    st.markdown(explanation)
                except Exception as e:
                    st.error(f"Erro: {e}")

# ====================== ABA – MODIFICAR / FOTO ======================
with tab_mod:
    st.subheader("🔧 Modificar circuito + Análise por foto")
    st.caption("Melhore amplificadores, adicione bateria, ou analise uma foto de placa")

    mod_mode = st.radio(
        "Modo",
        ["Presets de amplificador", "Sugestão livre (texto)", "Análise por foto"],
        horizontal=True,
    )

    interpreter = ElectronicsLLM(model=llm_model, temperature=llm_temp)

    if mod_mode == "Presets de amplificador":
        presets = list_modification_presets()
        preset_id = st.selectbox(
            "Modificação desejada",
            options=list(presets.keys()),
            format_func=lambda k: presets[k],
        )
        col_a, col_b = st.columns(2)
        with col_a:
            run_mod = st.button("▶ Aplicar e simular", type="primary", width="stretch")
        with col_b:
            explain = st.button("💡 Explicar com LLM", width="stretch")

        if run_mod or explain:
            try:
                original, modified, meta = apply_preset(preset_id)
                st.markdown(f"### {meta.title}")
                st.write(meta.description)

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Mudanças**")
                    for ch in meta.changes:
                        st.markdown(f"- {ch}")
                    st.markdown("**Benefícios**")
                    for b in meta.benefits:
                        st.markdown(f"- {b}")
                with c2:
                    st.markdown("**BOM a adicionar**")
                    for b in meta.bom_add:
                        st.markdown(f"- {b}")
                    st.markdown("**Avisos**")
                    for w in meta.warnings:
                        st.markdown(f"- ⚠️ {w}")

                if run_mod:
                    sim_o = CircuitSimulator("Original")
                    sim_o.circuit = original
                    sim_m = CircuitSimulator("Modificado")
                    sim_m.circuit = modified

                    with st.spinner("Simulando original e modificado..."):
                        res_o = sim_o.run_transient(step_time=1e-5, end_time=5e-3)
                        res_m = sim_m.run_transient(step_time=1e-5, end_time=5e-3)

                    scope_o = Oscilloscope("Original")
                    scope_o.load(res_o)
                    scope_m = Oscilloscope(meta.title)
                    scope_m.load(res_m)

                    g1, g2 = st.columns(2)
                    with g1:
                        st.plotly_chart(scope_o.plot(), width="stretch")
                    with g2:
                        st.plotly_chart(scope_m.plot(), width="stretch")

                if explain:
                    with st.spinner("Gerando explicação..."):
                        text = interpreter.suggest_modification(
                            "Amplificador de áudio inversor básico com carga de 8Ω",
                            meta.title + " — " + meta.description,
                        )
                        st.markdown(text)
            except Exception as e:
                st.error(f"Erro: {e}")
                st.info("Verifique se o ngspice está instalado e acessível.")

    elif mod_mode == "Sugestão livre (texto)":
        desc = st.text_area(
            "Descreva o circuito atual",
            value="Amplificador de áudio classe AB simples, alimentado por fonte 12V, carga 8Ω, ganho moderado.",
            height=100,
        )
        goal = st.text_area(
            "O que você quer melhorar?",
            value="Quero mais graves e volume, e se possível trocar a fonte por bateria recarregável de grafeno.",
            height=80,
        )
        if st.button("🧠 Sugerir modificações", type="primary"):
            with st.spinner("Analisando e sugerindo..."):
                try:
                    suggestion = interpreter.suggest_modification(desc, goal)
                    st.markdown(suggestion)
                except Exception as e:
                    st.error(f"Erro: {e}")

    else:  # Análise por foto
        st.markdown("#### Envie uma foto da placa / circuito")
        st.info(
            "Requer modelo de **visão** no Ollama (ex: `ollama pull llava` ou `moondream`). "
            "Modelos só-texto não conseguem ver a imagem."
        )
        vision_model = st.text_input("Modelo de visão Ollama", value="llava")
        uploaded = st.file_uploader("Foto do circuito", type=["png", "jpg", "jpeg", "webp"])
        extra_q = st.text_input(
            "Pergunta extra (opcional)",
            value="Como posso melhorar graves e adicionar bateria recarregável?",
        )

        if uploaded and st.button("📷 Analisar foto", type="primary"):
            with st.spinner(f"Analisando imagem com {vision_model}..."):
                try:
                    img_bytes = uploaded.read()
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    st.image(img_bytes, caption="Imagem enviada", width="stretch")
                    analysis = interpreter.analyze_circuit_photo(
                        b64, extra_question=extra_q, vision_model=vision_model
                    )
                    st.markdown("### Resultado da análise")
                    st.markdown(analysis)
                except Exception as e:
                    st.error(f"Erro: {e}")

# ====================== ABA – SOBRE ======================
with tab_about:
    st.markdown("""
## CircuitForge – Electronic Workbench 2.0

Projeto open-source para substituir e superar o clássico Electronic Workbench / Multisim
usando apenas ferramentas livres disponíveis no Linux (e multiplataforma).

### Stack
- **Simulação:** ngspice + PySpice
- **Circuitos de exemplo:** helpers Python (SKiDL-ready)
- **Instrumentos:** Osciloscópio e Bode com Plotly
- **Automação:** Parameter Sweep + Monte Carlo
- **LLM local:** Ollama com modelos leves (< 1 GB) especializados via prompt em:
  - Criação de pacotes / footprints
  - Leitura e descrição de circuitos e placas
  - Geração de netlists
  - Interpretação de formas de onda
  - **Modificação de circuitos + análise por foto**

### Modelos LLM recomendados
| Modelo          | Tamanho approx. | Uso recomendado          |
|-----------------|-----------------|--------------------------|
| qwen2:0.5b      | ~350 MB         | Melhor custo/benefício   |
| tinyllama       | ~637 MB         | Muito leve               |
| llama3.2:1b     | ~1.3 GB         | Limite superior          |

### Como rodar
```bash
# 1. Dependências de sistema
sudo apt install ngspice libngspice0-dev

# 2. Python
pip install -r requirements.txt

# 3. Ollama + modelo leve
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2:0.5b

# 4. App
streamlit run app/main.py
```

### Próximos passos
- Integração real com SKiDL para circuitos complexos
- Biblioteca de componentes com busca
- Drag-and-drop de esquemático
- Fine-tune de modelo leve em dataset de footprints + datasheets
- Exportação direta para KiCad
""")
