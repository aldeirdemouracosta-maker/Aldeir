#!/usr/bin/env python3
"""
Gera o dataset de fine-tune (formato messages/ShareGPT) a partir da própria biblioteca do CircuitForge.

Cada exemplo é VERIFICADO: os netlists são simulados no ngspice antes de entrar no dataset, e os
footprints vêm do gerador determinístico (sem reticências/placeholders).

Tarefas geradas
  1. criar_circuito  – pedido em português  → TITULO/ANALISE/SONDAS/netlist/EXPLICACAO (mesmo formato do app)
  2. explicar        – circuito + números   → explicação do instrutor
  3. footprint       – nome do pacote       → JSON com geometria + arquivo .kicad_mod
  4. quiz            – circuito             → perguntas em JSON

Uso:  python finetune/build_dataset.py [--variants 3] [--out finetune/dataset/electronics_sft.jsonl]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.footprints import build_footprint
from core.library import REGISTRY
from core.tutor import fmt, lesson_markdown, static_quiz
from llm.electronics_llm import CREATOR_SYSTEM, INSTRUCTOR_SYSTEM
from llm.validation import validate_netlist

PACKAGES = ["0201", "0402", "0603", "0805", "1206", "SOIC-8", "SOIC-14", "SOIC-16", "TSSOP-16", "TSSOP-20", "DIP-8", "DIP-14",
            "DIP-16", "DIP-28w", "TO-92", "SOT-23", "QFN-16", "QFN-32", "QFN-48", "header 1x4", "header 2x10"]
PHRASES = ["Crie o circuito: {s}", "Preciso simular: {n}. {s}", "Monte um netlist SPICE para {n}.", "Quero estudar {n}. Gere o circuito para simular."]


def analysis_line(spec: dict) -> str:
    k = spec["kind"]
    if k == "tran":
        return f"tran stop={spec['stop']:.4g} step={spec['step']:.4g}"
    if k == "ac":
        return f"ac start={spec['start']:.4g} stop={spec['stop']:.4g} points={spec.get('points', 20)}"
    if k == "dc":
        return f"dc src={spec['source']} start={spec['start']:.4g} stop={spec['stop']:.4g} step={spec['step']:.4g}"
    return "op"


def variants(cdef, n: int, rng: random.Random):
    yield cdef.defaults()
    for _ in range(n):
        p = {}
        for prm in cdef.params:
            if prm.key in ("n", "nbulk", "nmlcc") or (prm.min is not None and prm.max is not None and prm.max <= 1.0 and prm.min >= 0):
                p[prm.key] = prm.default
            else:
                p[prm.key] = prm.clamp(prm.default * rng.choice([0.5, 0.7, 1.5, 2.0]))
        yield p


def messages(system, user, assistant):
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user},
                         {"role": "assistant", "content": assistant}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "finetune/dataset/electronics_sft.jsonl"))
    ap.add_argument("--no-validate", action="store_true", help="não simula (útil sem ngspice)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    rows, skipped = [], 0

    for cdef in REGISTRY.values():
        for params in variants(cdef, a.variants, rng):
            netlist = cdef.netlist(params, with_helpers=False)
            spec = cdef.default_analysis(params)
            if not a.no_validate:
                v = validate_netlist(cdef.netlist(params), spec, timeout=60)
                if not v.ok:
                    skipped += 1
                    continue
            vals = ", ".join(f"{p.label} = {fmt(params[p.key], p.unit)}" for p in cdef.params[:4])
            user = rng.choice(PHRASES).format(s=cdef.summary, n=cdef.name) + f" Use: {vals}."
            probes = ", ".join(cdef.probes) or "out"
            reply = (f"TITULO: {cdef.name}\nANALISE: {analysis_line(spec)}\nSONDAS: {probes}\n```spice\n{netlist.strip()}\n```\n"
                     f"EXPLICACAO: {cdef.summary} {cdef.lesson.objetivo}")
            rows.append(messages(CREATOR_SYSTEM, user, reply))

        th = cdef.theory_values()
        user = (f"Circuito: {cdef.name}\nResumo: {cdef.summary}\nValores teóricos:\n" +
                "\n".join(f"- {k}: {fmt(v[0], v[1])}" for k, v in th.items()) + "\nExplique como funciona e o que observar.")
        rows.append(messages(INSTRUCTOR_SYSTEM, user, lesson_markdown(cdef)))

        q = static_quiz(cdef, n=2)
        if q:
            rows.append(messages(INSTRUCTOR_SYSTEM, f"Crie 2 perguntas de múltipla escolha sobre '{cdef.name}'. Responda em JSON.",
                                 json.dumps({"perguntas": q}, ensure_ascii=False)))

    for name in PACKAGES:
        fp = build_footprint(name)
        d = fp.to_dict()
        d.pop("pads", None)
        d["footprint_kicad"] = fp.to_kicad()
        sys_fp = "Você é um especialista em encapsulamentos eletrônicos e footprints (KiCad / IPC-7351). Responda com JSON válido."
        rows.append(messages(sys_fp, f"Gere a especificação de footprint para o pacote {name}.", json.dumps(d, ensure_ascii=False, indent=1)))

    rng.shuffle(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} exemplos gravados em {out} (descartados por falha na simulação: {skipped})")


if __name__ == "__main__":
    main()
