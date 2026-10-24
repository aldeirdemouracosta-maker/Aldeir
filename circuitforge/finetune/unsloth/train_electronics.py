#!/usr/bin/env python3
"""
CircuitForge – Fine-tune de modelo leve para eletrônica com Unsloth
=====================================================================
Modelo alvo: qwen2:0.5b / Qwen2-0.5B-Instruct (ou tinyllama / llama3.2:1b)

Requisitos:
  pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
  pip install --no-deps "trl<0.9.0" peft accelerate bitsandbytes

Uso:
  python train_electronics.py

Saída:
  ./electronics-lora/   ← adaptadores LoRA prontos para merge ou uso com Ollama
"""

from __future__ import annotations
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração – ajuste conforme sua GPU
# ---------------------------------------------------------------------------
MODEL_NAME = "unsloth/Qwen2-0.5B-Instruct"   # ~0.5B, cabe em 4-6 GB VRAM
# Alternativas:
# MODEL_NAME = "unsloth/tinyllama-chat"
# MODEL_NAME = "unsloth/Llama-3.2-1B-Instruct"

MAX_SEQ_LENGTH = 2048
LOAD_IN_4BIT = True          # QLoRA – essencial para GPU pequena
LORA_R = 16
LORA_ALPHA = 32
BATCH_SIZE = 2
GRAD_ACCUM = 4
EPOCHS = 3
LEARNING_RATE = 2e-4
OUTPUT_DIR = "./electronics-lora"
DATASET_PATH = "../dataset/electronics_sft.jsonl"

# ---------------------------------------------------------------------------
# Imports Unsloth
# ---------------------------------------------------------------------------
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

def main():
    print(f"Carregando modelo: {MODEL_NAME}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,               # auto
        load_in_4bit=LOAD_IN_4BIT,
    )

    # LoRA
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,           # Unsloth exige 0 para kernels otimizados
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    model.print_trainable_parameters()

    # Dataset
    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")

    def formatting_prompts_func(examples):
        """Converte o formato messages → texto único para SFT."""
        texts = []
        for messages in examples["messages"]:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True)

    # Trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            warmup_steps=10,
            num_train_epochs=EPOCHS,
            learning_rate=LEARNING_RATE,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=5,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir=OUTPUT_DIR,
            save_strategy="epoch",
            report_to="none",
        ),
    )

    print("Iniciando treino...")
    trainer.train()

    # Salva adaptadores LoRA
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"\n✓ Adaptadores salvos em: {OUTPUT_DIR}")

    # Opcional: merge e exportar para GGUF (para Ollama)
    # model.save_pretrained_merged("electronics-merged", tokenizer, save_method="merged_16bit")
    # model.save_pretrained_gguf("electronics-gguf", tokenizer, quantization_method="q4_k_m")

    print("""
Próximos passos:
  1. Teste o modelo com os adaptadores.
  2. Para usar no Ollama:
       - Faça merge (save_pretrained_merged)
       - Converta para GGUF
       - Crie um Modelfile apontando para o GGUF
  3. Ou carregue os adaptadores LoRA diretamente com PEFT em runtime.
""")


if __name__ == "__main__":
    main()
