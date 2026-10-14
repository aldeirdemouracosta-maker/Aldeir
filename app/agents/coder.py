"""Agente CODER: gera, explica, revisa e propõe código. Nunca altera arquivos."""
from __future__ import annotations

from typing import Any

from app.agents.base import TextAgent

_SYSTEMS = {
    "code_generate": "Gere código correto e conciso. Responda com o código e breve nota.",
    "code_explain": "Explique o código de forma clara e objetiva.",
    "code_review": "Revise o código: bugs, riscos e melhorias, em lista curta.",
    "code_propose": "Proponha a modificação como diff unificado. Não afirme ter aplicado nada.",
}


class CoderAgent(TextAgent):
    name = "coder"
    actions = tuple(_SYSTEMS)
    description = "Geração, explicação, revisão e proposta de código (somente texto)."

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        return await self.provider.generate(
            self.model, self.text_of(payload), system=_SYSTEMS[action])
