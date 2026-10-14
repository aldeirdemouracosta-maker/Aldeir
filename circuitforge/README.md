# CircuitForge – Electronic Workbench 2.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Laboratório de eletrônica **open-source**: simulador SPICE (ngspice) com instrumentos virtuais, **57 circuitos prontos**
e um **instrutor/criador de circuitos mediado por IA local** (Ollama) — acionado **apenas quando você clica no botão 🤖**.

## O que tem

| Área | Exemplos |
|---|---|
| 🔌 Fundamentos | filtros RC, RLC, divisor, retificadores, amp-op, emissor-comum, 555 |
| 🔋 Fontes | Zener, regulador série, LDO com PMOS, buck, boost, retificador com filtro, fonte linear completa (trafo+ponte+regulador) |
| 💻 Placas de computador | VRM de CPU de 2 fases, LDO USB 5 V→3,3 V, impedância da PDN/desacoplamento, I²C, reset de energização, oscilador em anel |
| 🧠 IA | neurônio analógico (soma + tanh), crossbar resistivo (multiplicação matriz-vetor), front-end de sensor para TinyML, VRM de acelerador |
| 🔊 Som | pré-amp, classe AB (com THD), classe D (PWM+LC), crossover de 2 vias |
| 🎸 Pedais | clean boost, overdrive estilo Tube Screamer, fuzz, wah, tremolo |
| ☀️ Solar | curva I-V/P-V do painel, carregador buck com MPPT manual, sombreamento e diodos de bypass |
| 🚗 Veículos | carregador USB, load dump + TVS, alternador trifásico, relé com flyback, dimmer PWM de LED, proteção de polaridade |
| 📻 Rádio/TV | detector AM, sintonia LC, misturador super-heteródino, separador de sincronismo de TV, oscilador Colpitts |
| 📡 Antenas | dipolo (ROE/VSWR), transformador λ/4, casador L, filtro passa-faixa de FM, balun 4:1 de TV |

Lista completa: [`docs/CATALOGO.md`](docs/CATALOGO.md).

Cada circuito traz **parâmetros editáveis (notação 4.7k, 100n)**, **netlist editável**, **valores teóricos** para comparar com a
simulação, uma **lição** (objetivo, teoria, o que observar, experimentos) e quiz — tudo funciona **sem IA**.

## Instrutor e Criador com IA local

Ative **Recursos de IA** na barra lateral. Cada botão 🤖 chama o modelo local somente naquele momento:

* **Explicar este circuito** – explicação passo a passo com os *seus* parâmetros e medições.
* **Gerar quiz / Interpretar forma de onda / Perguntar ao instrutor.**
* **Criar circuito com IA** – você descreve (“pedal fuzz com 2 transistores”); o modelo escreve o netlist, o **ngspice valida e
  simula**; se der erro, a mensagem volta ao modelo para corrigir (até 5 tentativas). Exemplos reais da biblioteca são
  fornecidos ao modelo como referência. Se não conseguir, o app sugere o circuito mais parecido da biblioteca.
* **Footprints:** a geometria vem de um gerador determinístico (SOIC, TSSOP, DIP, QFN, TO-92, SOT-23, chips 0201–1210,
  barras de pinos); a IA só escreve notas de uso.

Segurança: todo netlist (inclusive o da IA) é sanitizado – `.control`, `.include`, `.lib`, leitura/escrita de arquivos e
comandos de shell são removidos ou recusados.

> Modelos < 1 GB (ex.: `qwen2:0.5b`) explicam bem, mas erram mais ao criar circuitos. Recomendado: `qwen2.5:1.5b` ou
> `qwen2.5-coder:1.5b`. O fine-tune opcional está em [`finetune/`](finetune/README.md).

## Instalação

```bash
sudo apt install -y ngspice                 # macOS: brew install ngspice
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/main.py

# IA local (opcional)
curl -fsSL https://ollama.com/install.sh | sh && ollama pull qwen2.5:1.5b
```

### Docker
```bash
docker compose up --build
docker compose exec ollama ollama pull qwen2.5:1.5b
```

## Usar como biblioteca

```python
from core.library import get
from core.simulator import CircuitSimulator
from instruments import BodePlotter

c = get("rc_lowpass"); p = {"r": 1e3, "c": 100e-9}
sim = CircuitSimulator(); sim.load_circuit(c, p)
res = sim.run(c.analysis_options(p)["AC (Bode)"])
sim.load_netlist("Meu\nV1 in 0 DC 10\nR1 in out 1k\nR2 out 0 3k\n")      # netlist livre
print(sim.run_operating_point()["out"])
```
Veja também `examples/rc_demo.py`, `automation/` (varredura e Monte Carlo reais) e `instruments/` (osciloscópio com medições e THD,
analisador de espectro, Bode com −3 dB para passa-baixa/alta/faixa, analisador de ROE).

## Estrutura

```
app/main.py              interface Streamlit (7 abas)
core/spice_engine.py     ngspice em modo batch + sanitização + leitor de .raw
core/simulator.py        CircuitSimulator (load_netlist, tran/ac/dc/op)
core/library/            57 circuitos por categoria (+ lições e fórmulas)
core/footprints.py       gerador de footprints KiCad
core/tutor.py            lição e quiz offline
instruments/             scope, spectrum/THD, bode, RF
automation/              ParameterSweep, MonteCarlo, métricas
llm/                     cliente Ollama, criador com validação, instrutor, recuperação na biblioteca
finetune/                build_dataset.py (verificado no ngspice), Unsloth, LLaMA-Factory
tests/                   120 testes (valores teóricos, sanitização, LLM simulado)
```

## Testes

```bash
pip install -r requirements-dev.txt && pytest -q
```
Os testes simulam **todos** os circuitos e conferem valores analíticos (fc do RC, ganho do amp-op, frequência do 555, Vout do
buck/boost, pico do wah, Γ do casador λ/4, curva do painel...). O LLM é simulado com um cliente falso: nenhum teste exige Ollama.

## Limitações honestas

* Modelos comportamentais/didáticos: amp-op de 1 polo, chaves ideais, BJT/MOSFET genéricos. Não substitui modelos de fabricante
  nem teste em bancada.
* Conversores (buck/boost/VRM) estão em **malha aberta** (ciclo de trabalho fixo): mostram o princípio, não a regulação de um controlador real.
* Antenas são circuitos equivalentes concentrados, não simulação eletromagnética.
* Os scripts de fine-tune exigem GPU e não foram executados no ambiente de desenvolvimento.

## Licença

MIT.
