"""Planejador determinístico: pedido em português → etapas para agentes.

Modo ``rules`` (sem modelo). Um coordenador LLM pode propor etapas no
mesmo formato; ``validate_steps`` confere IDs e parâmetros antes de
qualquer execução.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .registry import BY_ID, Assignment

ORDER = ["gerador", "cortador", "editor_generativo", "silencios", "audio", "cenas",
         "interpolador", "upscaler", "escala", "transcritor", "legendas", "exportador"]

TIME = r"(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)"
RES = {"480p": 480, "720p": 720, "1080p": 1080, "full hd": 1080, "1440p": 1440, "2k": 1440, "4k": 2160, "2160p": 2160}


@dataclass
class Step:
    agente: str
    params: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"agente": self.agente, "params": dict(self.params)}


@dataclass
class Plan:
    pedido: str
    etapas: List[Step]
    avisos: List[str] = field(default_factory=list)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _seconds(ts: str) -> float:
    parts = [float(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def plan_rules(pedido: str) -> Plan:
    t = _norm(pedido)
    steps: Dict[str, Step] = {}
    avisos: List[str] = []

    m = re.search(rf"{TIME}\s*(?:ate|a|-|–)\s*{TIME}", t)
    if re.search(r"\bcort|trecho|recort", t) or m:
        if m:
            ini, fim = _seconds(m.group(1)), _seconds(m.group(2))
            if fim <= ini:
                avisos.append("tempo final do corte é menor ou igual ao inicial; corte ignorado")
            else:
                steps["cortador"] = Step("cortador", {"inicio": ini, "fim": fim})
        else:
            avisos.append("pedido de corte sem tempos no formato HH:MM:SS até HH:MM:SS")
    if re.search(r"silencio|pausa", t):
        steps["silencios"] = Step("silencios", {"margem_s": 0.2})
    if re.search(r"ruido|chiado|limp\w* (o )?audio|melhor\w* (o )?audio", t):
        steps["audio"] = Step("audio", {"reduzir_ruido": True, "normalizar": True})
    elif re.search(r"normaliz|volume", t):
        steps["audio"] = Step("audio", {"reduzir_ruido": False, "normalizar": True})
    if re.search(r"\bcenas?\b", t):
        steps["cenas"] = Step("cenas", {"limiar": 0.4})
    if re.search(r"camera lenta|slow ?motion|interpol|suaviz|60 ?fps|mais quadros", t):
        fator = 4 if re.search(r"4x|quatro vezes|super lenta", t) else 2
        steps["interpolador"] = Step("interpolador", {"fator": fator, "camera_lenta": bool(re.search(r"lenta|slow", t))})
    altura = next((h for k, h in RES.items() if k in t), None)
    mres = re.search(r"\b(\d{3,4})p\b", t)
    if mres and 144 <= int(mres.group(1)) <= 4320:
        altura = int(mres.group(1))
    if altura or re.search(r"upscal|aument\w* (a )?resolucao|melhor\w* (a )?(qualidade|resolucao)", t):
        agente = "escala" if re.search(r"sem ia|rapido", t) else "upscaler"
        steps[agente] = Step(agente, {"altura": altura or 1080})
    if re.search(r"legend", t):
        steps["transcritor"] = Step("transcritor", {"idioma": "pt"})
        steps["legendas"] = Step("legendas", {"embutir": True})
    elif re.search(r"transcrev|transcri", t):
        steps["transcritor"] = Step("transcritor", {"idioma": "pt"})
    if re.search(r"\b(gere|gerar|crie|criar)\b.*\bvideo", t):
        steps["gerador"] = Step("gerador", {"prompt": pedido})
    # "remova o carro" é edição generativa; "remova os silêncios/o ruído" não.
    alvos = re.findall(r"\bremov\w* (?:a|o|as|os|essa|esse|essas|esses) (\w+)", t)
    remove_objeto = any(not re.match(r"silencio|pausa|ruido|chiado|eco|trecho|parte|inicio|final|fim", w)
                        for w in alvos)
    if re.search(r"troqu\w* o fundo|substitu", t) or remove_objeto:
        steps["editor_generativo"] = Step("editor_generativo", {"prompt": pedido})

    if not steps:
        avisos.append("nenhuma tarefa reconhecida; reformule (ex.: 'retire os silêncios e coloque legendas')")
    else:
        steps["exportador"] = Step("exportador", {"crf": 20})
    ordered = [steps[a] for a in ORDER if a in steps]
    return Plan(pedido, ordered, avisos)


def validate_steps(raw: List[Dict]) -> List[Step]:
    """Valida etapas propostas por um coordenador LLM (IDs e tipos)."""
    allowed = {
        "cortador": {"inicio": float, "fim": float}, "silencios": {"margem_s": float},
        "audio": {"reduzir_ruido": bool, "normalizar": bool}, "cenas": {"limiar": float},
        "interpolador": {"fator": int, "camera_lenta": bool}, "upscaler": {"altura": int},
        "escala": {"altura": int}, "transcritor": {"idioma": str}, "legendas": {"embutir": bool},
        "exportador": {"crf": int}, "gerador": {"prompt": str}, "editor_generativo": {"prompt": str},
    }
    out = []
    for item in raw:
        agent = item.get("agente")
        if agent not in allowed:
            raise ValueError(f"agente desconhecido: {agent!r}")
        params = {}
        for k, v in (item.get("params") or {}).items():
            typ = allowed[agent].get(k)
            if typ is None:
                raise ValueError(f"parâmetro não permitido para {agent}: {k}")
            if typ is float and isinstance(v, int) and not isinstance(v, bool):
                v = float(v)
            if not isinstance(v, typ) or (typ is int and isinstance(v, bool)):
                raise ValueError(f"tipo inválido em {agent}.{k}")
            params[k] = v
        out.append(Step(agent, params))
    return sorted(out, key=lambda s: ORDER.index(s.agente))


def explain(plan: Plan, assignments: Dict[str, Assignment]) -> str:
    lines = [f"Pedido: {plan.pedido}", ""]
    if not plan.etapas:
        lines.append("Nenhuma etapa planejada.")
    for i, step in enumerate(plan.etapas, 1):
        a = assignments.get(step.agente)
        agent = BY_ID[step.agente]
        where = f"{a.device.id} ({a.device.kind})" if a and a.device else "sem dispositivo"
        status = "pronto" if a and a.disponivel else "INDISPONÍVEL"
        params = ", ".join(f"{k}={v}" for k, v in step.params.items() if k != "prompt")
        lines.append(f"{i}. {agent.nome} — {agent.papel}")
        lines.append(f"   dispositivo: {where} · estado: {status}" + (f" · {params}" if params else ""))
        for motivo in (a.motivos if a else []):
            lines.append(f"   - {motivo}")
    for av in plan.avisos:
        lines.append(f"Aviso: {av}")
    blocked = [s.agente for s in plan.etapas if not (assignments.get(s.agente) and assignments[s.agente].disponivel)]
    lines.append("")
    if blocked:
        lines.append(f"Bloqueado: {', '.join(BY_ID[b].nome for b in blocked)} — o plano não pode rodar inteiro.")
    else:
        lines.append("Nada foi executado. Confirme para executar.")
    return "\n".join(lines)


def first_unavailable(plan: Plan, assignments: Dict[str, Assignment]) -> Optional[str]:
    for s in plan.etapas:
        a = assignments.get(s.agente)
        if not (a and a.disponivel):
            return s.agente
    return None
