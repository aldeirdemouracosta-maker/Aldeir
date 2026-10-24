# CircuitForge – Fine-tune do LLM de Eletrônica

Três artefatos prontos para você analisar um a um.

---

## 1. Dataset de exemplo (`dataset/electronics_sft.jsonl`)

Formato **ShareGPT / messages** (compatível com Unsloth, LLaMA-Factory, Axolotl, TRL).

Contém ~15 exemplos cobrindo:

- Criação de footprints / pacotes (SOIC, QFN, TO-92, 0805, ESP32, LED, 7805…)
- Leitura e descrição de circuitos (RC, op-amp, retificador, emissor-comum)
- Geração de netlist SPICE

**Como expandir:** adicione mais linhas no mesmo formato JSONL.  
Quanto mais exemplos de qualidade (especialmente footprints reais do KiCad + datasheets), melhor o modelo fica.

Arquivo auxiliar: `dataset_info.json` (necessário para LLaMA-Factory).

---

## 2. Script Unsloth (`unsloth/train_electronics.py`)

- Modelo padrão: **Qwen2-0.5B-Instruct**
- Método: **QLoRA** (4-bit) → roda em GPU de 4–8 GB
- Salva adaptadores LoRA em `./electronics-lora/`

```bash
cd finetune/unsloth
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps "trl<0.9.0" peft accelerate bitsandbytes datasets
python train_electronics.py
```

Depois do treino você pode:
- Usar os adaptadores LoRA com PEFT
- Fazer merge + converter para GGUF e carregar no Ollama

---

## 3. Configuração LLaMA-Factory (`llamafactory/electronics_lora.yaml`)

Interface mais amigável (inclusive WebUI).

```bash
# Instalação
pip install "llamafactory[torch,metrics]"
# ou clone o repositório

# Treino via CLI
llamafactory-cli train electronics_lora.yaml

# Ou abra a interface web
llamafactory-cli webui
# → carregue o YAML ou configure manualmente apontando para o dataset
```

Lembre-se de copiar/ajustar o `dataset_dir` e registrar o dataset (o `dataset_info.json` já está pronto).

---

## Ordem sugerida de análise

1. **Dataset** → veja a qualidade e o formato dos exemplos  
2. **Unsloth** → script completo, mais rápido e econômico em VRAM  
3. **LLaMA-Factory** → configuração YAML + possibilidade de WebUI

Qualquer um dos dois frameworks serve. Unsloth costuma ser a melhor escolha para modelos < 1–2B em GPU de consumidor.
