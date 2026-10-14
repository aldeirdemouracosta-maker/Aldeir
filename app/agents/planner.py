"""Agente PLANNER/TOOL: planeja e executa uma sequência curta de ações já registradas.

Regras (simples e previsíveis):
- só pode chamar ações registradas e habilitadas, nunca as suas próprias (sem recursão);
- no máximo MAX_STEPS passos, executados em ordem; para no primeiro erro;
- `{{prev}}` em valores de texto do payload é trocado pela saída do passo anterior (troca literal, sem eval);
- plan_create só PROPÕE (JSON validado); nada roda até um plan_run explícito;
- nenhuma ação altera arquivos: o Coder só devolve texto e o terminal supervisionado não é um agente.
"""
from __future__ import annotations

import json
import re
from typing import Any
from collections.abc import Awaitable, Callable

from app.agents.base import TextAgent
from app.core.models import OutputError
from app.core.registry import AgentRegistry

MAX_STEPS = 5
MAX_PLAN_BYTES = 8_000
OWN_ACTIONS = ("plan_create", "plan_run")
RunStep = Callable[[str, dict[str, Any]], Awaitable[str]]


class PlanError(OutputError):
    pass


class RunContext:
    """Ponte tardia: o orquestrador só existe depois dos agentes."""
    run_step: RunStep | None = None


def validate_plan(steps: Any, allowed: set[str]) -> list[dict]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise PlanError(f"o plano deve ter de 1 a {MAX_STEPS} passos")
    if len(json.dumps(steps)) > MAX_PLAN_BYTES:
        raise PlanError("plano grande demais")
    clean = []
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict) or set(st) - {"action", "payload"}:
            raise PlanError(f"passo {i}: use somente 'action' e 'payload'")
        action, payload = st.get("action"), st.get("payload", {})
        if action in OWN_ACTIONS:
            raise PlanError(f"passo {i}: o planner não pode chamar a si mesmo")
        if action not in allowed:
            raise PlanError(f"passo {i}: ação não permitida ou desabilitada: {action!r}")
        if not isinstance(payload, dict):
            raise PlanError(f"passo {i}: payload deve ser objeto")
        clean.append({"action": action, "payload": payload})
    return clean


def parse_plan_json(text: str) -> Any:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    body = (m.group(1) if m else text).strip()
    try:
        return json.loads(body)
    except ValueError as e:
        raise PlanError(f"o modelo não devolveu JSON válido: {e}") from e


def _fill(payload: dict, prev: str) -> dict:
    return {k: v.replace("{{prev}}", prev) if isinstance(v, str) else v for k, v in payload.items()}


class PlannerAgent(TextAgent):
    name = "planner"
    actions = OWN_ACTIONS
    description = "Planeja (JSON validado) e executa até 5 passos entre as ações registradas."

    def __init__(self, provider, model: str, registry: AgentRegistry, ctx: RunContext) -> None:
        super().__init__(provider, model)
        self.registry, self.ctx = registry, ctx

    def allowed(self) -> set[str]:
        return {a for a in self.registry.actions() if a not in OWN_ACTIONS}

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        if action == "plan_create":
            return await self._create(self.text_of(payload))
        return await self._execute(payload.get("steps"))

    async def _create(self, goal: str) -> str:
        tools = "\n".join(f"- {a} (agente {self.registry.owner_of(a)})" for a in sorted(self.allowed()))
        system = ("Responda SOMENTE com um array JSON de passos: "
                  '[{"action": "...", "payload": {...}}]. Use apenas estas ações:\n' + tools +
                  f"\nNo máximo {MAX_STEPS} passos. Use \"{{{{prev}}}}\" para a saída do passo anterior.")
        steps = validate_plan(parse_plan_json(await self.provider.generate(self.model, goal, system=system)),
                              self.allowed())
        return json.dumps(steps, ensure_ascii=False, indent=2)

    async def _execute(self, steps: Any) -> str:
        if self.ctx.run_step is None:
            raise PlanError("execução de passos indisponível")
        plan, prev, lines = validate_plan(steps, self.allowed()), "", []
        for i, st in enumerate(plan, 1):
            try:
                prev = await self.ctx.run_step(st["action"], _fill(st["payload"], prev))
            except Exception as e:  # para no primeiro erro e diz onde
                lines.append(f"{i}. {st['action']} → ERRO: {e}")
                lines.append(f"plano interrompido no passo {i} de {len(plan)}")
                return "\n".join(lines)
            lines.append(f"{i}. {st['action']} → {prev[:300]}")
        return "\n".join(lines)
