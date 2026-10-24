# CircuitForge – Electronic Workbench 2.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)](https://streamlit.io)

Aplicativo **open-source** de simulação de circuitos eletrônicos com instrumentos virtuais, automação e **LLM local leve (&lt; 1 GB)** especializado em:

- Criação de pacotes / footprints eletrônicos (KiCad / IPC)
- Leitura e descrição de circuitos e placas
- Geração de netlists SPICE
- Interpretação de formas de onda

Substitui e supera o clássico Electronic Workbench / Multisim usando apenas ferramentas livres.

---

## Recursos

| Módulo | Descrição |
|--------|-----------|
| **Simulação SPICE** | ngspice + PySpice (DC, AC, Transient, Operating Point) |
| **Circuitos de exemplo** | 12 circuitos prontos (RC, RLC, retificadores, op-amps, BJT, 555…) |
| **Instrumentos virtuais** | Osciloscópio e Diagrama de Bode interativos (Plotly) |
| **Automação** | Parameter Sweep + Monte Carlo |
| **LLM local** | Ollama + modelos leves para footprints, leitura de circuitos e netlists |
| **Fine-tune** | Dataset + scripts Unsloth e LLaMA-Factory prontos |

---

## Requisitos

- Linux (recomendado) / macOS / Windows
- Python 3.11+
- ngspice (`sudo apt install ngspice libngspice0-dev`)
- Ollama (para o LLM local)

---

## Instalação rápida

```bash
# Dependências de sistema (Debian/Ubuntu)
sudo apt update
sudo apt install -y ngspice libngspice0-dev

# Python
cd circuitforge   # pasta do projeto
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Ollama + modelo leve (< 1 GB)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2:0.5b             # ~350 MB – recomendado

# Rodar a interface
streamlit run app/main.py
```

---

## Docker

```bash
docker build -t circuitforge .
docker run -p 8501:8501 -v $(pwd)/.cache:/app/.cache circuitforge
```

---

## Estrutura do projeto

```
circuitforge/
├── app/
│   └── main.py                 # Interface Streamlit (5 abas)
├── core/
│   ├── simulator.py            # Motor PySpice / ngspice
│   └── netlist.py              # 12 circuitos de exemplo
├── instruments/
│   ├── scope.py                # Osciloscópio virtual
│   └── bode.py                 # Diagrama de Bode
├── automation/
│   ├── sweep.py                # Varredura de parâmetros
│   └── montecarlo.py           # Análise Monte Carlo
├── llm/
│   └── electronics_llm.py      # LLM local especializado
├── finetune/
│   ├── dataset/                # Dataset ShareGPT (JSONL)
│   ├── unsloth/                # Script de fine-tune Unsloth
│   └── llamafactory/           # Config YAML LLaMA-Factory
├── examples/
│   └── rc_demo.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## LLM – Modelos leves recomendados

| Modelo       | Tamanho approx. | Observação             |
|--------------|-----------------|------------------------|
| qwen2:0.5b   | ~350 MB         | Melhor custo/benefício |
| tinyllama    | ~637 MB         | Extremamente leve      |
| llama3.2:1b  | ~1.3 GB         | Limite superior        |

O módulo `ElectronicsLLM` usa prompt engineering forte.  
Há um pipeline completo de fine-tune (dataset + Unsloth + LLaMA-Factory) na pasta `finetune/`.

---

## Fine-tune (opcional)

```bash
cd finetune
# Ver README.md da pasta para instruções Unsloth ou LLaMA-Factory
```

---

## Licença

MIT – use, modifique e distribua livremente.

---

## Contribuições

Pull requests são bem-vindos! Abra uma issue antes de mudanças grandes.


---

## Testes

```bash
pip install -r requirements.txt
python -m pytest tests
```

Cobre os 15 circuitos de exemplo (OP/Transient/AC), valores físicos esperados
(divisor, corte do RC, ganho do op-amp, retificadores, 555, termostato),
netlist em texto, varredura, Monte Carlo, módulo LLM (Ollama simulado) e a
interface Streamlit.

> A simulação usa o `ngspice` via linha de comando (compatível com ngspice 42+);
> o PySpice é usado apenas para montar os circuitos.
