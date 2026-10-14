# Fine-tune do LLM de eletrônica

O CircuitForge funciona com qualquer modelo do Ollama. O fine-tune é **opcional** e serve para melhorar,
principalmente, o **Criador de circuitos** em modelos pequenos (0,5–1,5 B).

## 1. Gerar o dataset (verificado)

```bash
python finetune/build_dataset.py            # ~360 exemplos, todos simulados no ngspice
```

O script percorre a biblioteca (57 circuitos × variações de parâmetros) e gera, no formato `messages`:

| Tarefa | Entrada | Saída |
|---|---|---|
| `criar_circuito` | pedido em português | `TITULO/ANALISE/SONDAS/netlist/EXPLICACAO` (mesmo formato do app) |
| `explicar` | circuito + valores teóricos | lição do instrutor |
| `quiz` | circuito | perguntas em JSON |
| `footprint` | nome do pacote | JSON + `.kicad_mod` **real** (gerador determinístico) |

Netlists que não simulam são descartados (`--no-validate` desliga a checagem). Para ampliar: adicione
circuitos em `core/library/` – o dataset cresce junto, sempre consistente com o simulador.

## 2. Treinar (GPU CUDA necessária)

**Unsloth (QLoRA, 4–8 GB de VRAM):**
```bash
pip install -r finetune/requirements-finetune.txt
python finetune/unsloth/train_electronics.py --model unsloth/Qwen2.5-1.5B-Instruct --gguf
```

**LLaMA-Factory (YAML/WebUI):**
```bash
cd finetune/llamafactory && llamafactory-cli train electronics_lora.yaml
```

## 3. Usar no Ollama

```bash
cat > Modelfile <<'EOT'
FROM ./electronics-gguf/unsloth.Q4_K_M.gguf
PARAMETER temperature 0.2
EOT
ollama create circuitforge -f Modelfile
```
Depois selecione `circuitforge` na barra lateral do app.

> Estes scripts não foram executados no ambiente de desenvolvimento (sem GPU). O dataset e o restante do
> projeto são testados (`pytest`).
