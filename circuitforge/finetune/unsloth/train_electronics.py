#!/usr/bin/env python3
"""
CircuitForge – fine-tune (QLoRA) de um modelo leve para eletrônica com Unsloth.

Antes: gere o dataset (verificado no ngspice):   python finetune/build_dataset.py
Uso:   python finetune/unsloth/train_electronics.py [--model unsloth/Qwen2.5-1.5B-Instruct] [--epochs 3]

Saída: ./electronics-lora (adaptadores) e, com --gguf, ./electronics-gguf (q4_k_m) pronto para o Ollama.

NOTA: este script precisa de GPU CUDA e NÃO foi executado no ambiente de desenvolvimento do projeto.
As APIs do TRL mudam entre versões; o código tenta as duas assinaturas conhecidas.
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="unsloth/Qwen2.5-1.5B-Instruct")      # alternativa leve: unsloth/Qwen2.5-0.5B-Instruct
    ap.add_argument("--data", default=str(HERE.parent / "dataset" / "electronics_sft.jsonl"))
    ap.add_argument("--out", default="./electronics-lora")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--max-seq", type=int, default=3072)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--gguf", action="store_true", help="exporta GGUF q4_k_m após o treino")
    a = ap.parse_args()

    from unsloth import FastLanguageModel  # noqa: E402  (import tardio: exige GPU)
    import torch
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(model_name=a.model, max_seq_length=a.max_seq, dtype=None, load_in_4bit=True)
    model = FastLanguageModel.get_peft_model(
        model, r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0, bias="none", random_state=42,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth")

    ds = load_dataset("json", data_files=a.data, split="train")
    ds = ds.map(lambda ex: {"text": [tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False) for m in ex["messages"]]},
                batched=True, remove_columns=ds.column_names)
    split = ds.train_test_split(test_size=0.05, seed=42)

    cfg = SFTConfig(
        dataset_text_field="text", max_seq_length=a.max_seq, packing=False,
        per_device_train_batch_size=a.batch, gradient_accumulation_steps=a.accum, warmup_ratio=0.05,
        num_train_epochs=a.epochs, learning_rate=a.lr, logging_steps=5, optim="adamw_8bit", weight_decay=0.01,
        lr_scheduler_type="cosine", seed=42, output_dir=a.out, save_strategy="epoch", report_to="none",
        bf16=torch.cuda.is_bf16_supported(), fp16=not torch.cuda.is_bf16_supported(),
        eval_strategy="epoch", per_device_eval_batch_size=a.batch)
    kwargs = dict(model=model, train_dataset=split["train"], eval_dataset=split["test"], args=cfg)
    try:
        trainer = SFTTrainer(processing_class=tokenizer, **kwargs)     # TRL ≥ 0.12
    except TypeError:
        trainer = SFTTrainer(tokenizer=tokenizer, **kwargs)            # TRL antigo

    trainer.train()
    model.save_pretrained(a.out)
    tokenizer.save_pretrained(a.out)
    print(f"✓ Adaptadores LoRA em {a.out}")
    if a.gguf:
        model.save_pretrained_gguf("electronics-gguf", tokenizer, quantization_method="q4_k_m")
        print("✓ GGUF em ./electronics-gguf  →  crie um Modelfile (FROM ./electronics-gguf/...gguf) e rode `ollama create circuitforge -f Modelfile`")


if __name__ == "__main__":
    main()
