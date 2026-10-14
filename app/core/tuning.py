"""Avaliação e ajuste (autotreinamento SEM tocar nos pesos).

Ciclo: suíte de casos por agente (evals/*.yaml) → mede acerto e latência de cada modelo candidato →
guarda no StateStore → recomenda o melhor. Trocar o modelo exige pedido explícito (nunca é automático).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.models import SwarmError
from app.core.state import StateStore

MIN_SCORE = 0.5      # abaixo disso nenhum candidato é recomendado
MARGIN = 0.1         # o candidato precisa superar o atual por esta margem (evita troca por ruído)


class SuiteError(SwarmError):
    pass


@dataclass
class Suite:
    agent: str
    cases: list[dict]
    sha: str


def load_suite(agent: str, directory: Path) -> Suite:
    p = directory / f"{agent}.yaml"
    if not p.is_file():
        raise SuiteError(f"sem suíte de avaliação para {agent!r} ({p.name})")
    raw = p.read_bytes()
    cases = (yaml.safe_load(raw) or {}).get("cases", [])
    for c in cases:
        if not {"id", "action", "payload", "check"} <= set(c):
            raise SuiteError(f"caso inválido em {p.name}: {c.get('id', '?')}")
    return Suite(agent, cases, hashlib.sha256(raw).hexdigest()[:12])


def check_output(output: str, spec: dict) -> tuple[bool, str]:
    low = output.lower()
    for s in spec.get("contains", []):
        if str(s).lower() not in low:
            return False, f"faltou {s!r}"
    for s in spec.get("not_contains", []):
        if str(s).lower() in low:
            return False, f"não devia conter {s!r}"
    if "regex" in spec and not re.search(spec["regex"], output):
        return False, "regex não casou"
    if "max_chars" in spec and len(output) > spec["max_chars"]:
        return False, f"{len(output)} caracteres (máx {spec['max_chars']})"
    if spec.get("json"):
        try:
            json.loads(output)
        except ValueError:
            return False, "JSON inválido"
    return True, ""


async def evaluate(agent, suite: Suite, timeout: float = 120.0) -> dict:
    """Roda todos os casos num agente já construído com o modelo candidato."""
    passed, latencies, fails = 0, [], []
    for c in suite.cases:
        t0 = time.perf_counter()
        try:
            out = await asyncio.wait_for(agent.run(c["action"], dict(c["payload"])), timeout)
            ok, why = check_output(out, c["check"])
        except Exception as e:  # erro do modelo/provedor conta como falha do caso
            ok, why = False, f"erro: {e}"
        latencies.append((time.perf_counter() - t0) * 1000)
        passed += ok
        if not ok:
            fails.append(f"{c['id']}: {why}")
    return {"passed": passed, "total": len(suite.cases), "latency_ms": round(statistics.median(latencies)),
            "fails": fails}


@dataclass
class Recommendation:
    model: str | None
    reason: str


def recommend(rows: list[dict], current: str) -> Recommendation:
    """rows: avaliações mais recentes por modelo (mesma suíte). Escolhe por acerto e depois latência."""
    if not rows:
        return Recommendation(None, "sem avaliações")
    score = lambda r: r["passed"] / r["total"]
    best = sorted(rows, key=lambda r: (-score(r), r["latency_ms"]))[0]
    cur = next((r for r in rows if r["model"] == current), None)
    if score(best) < MIN_SCORE:
        return Recommendation(None, f"nenhum candidato chega a {MIN_SCORE:.0%} (melhor: {best['model']} {score(best):.0%})")
    if best["model"] == current:
        return Recommendation(None, f"manter {current} ({score(best):.0%})")
    if cur and score(best) - score(cur) < MARGIN:
        return Recommendation(None, f"{best['model']} não supera {current} por {MARGIN:.0%}; manter")
    return Recommendation(best["model"], f"{best['model']} {score(best):.0%} @ {best['latency_ms']} ms"
                          + (f" (atual {current}: {score(cur):.0%})" if cur else ""))


def record(store: StateStore, suite: Suite, model: str, result: dict) -> None:
    store.add_eval(suite.agent, model, suite.sha, result["passed"], result["total"], result["latency_ms"])
