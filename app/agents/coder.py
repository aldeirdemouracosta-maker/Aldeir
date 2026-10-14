"""Agente CODER: gera, explica, revisa e propõe código. Nunca altera arquivos."""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import TextAgent
from app.core.models import OutputError

_SYSTEMS = {
    "code_generate": "Gere código correto e conciso. Responda com o código e breve nota.",
    "code_explain": "Explique o código de forma clara e objetiva.",
    "code_review": "Revise o código: bugs, riscos e melhorias, em lista curta.",
    "code_propose": "Proponha a modificação como diff unificado. Não afirme ter aplicado nada.",
}


class CodeFormatError(OutputError):
    pass


_FENCE = re.compile(r"^```[\w+.-]*\n(.*?)\n?```$", re.DOTALL)


def enforce_code_only(text: str) -> str:
    """Aceita só código: um único bloco cercado (cerca removida) ou código puro sem cercas.
    Prosa fora do bloco, vários blocos ou cercas soltas são rejeitados."""
    t = text.strip()
    m = _FENCE.match(t)
    if m and "```" not in m.group(1):
        return m.group(1).rstrip("\n") + "\n"
    if "```" in t:
        raise CodeFormatError("resposta contém Markdown ou explicação fora do código")
    return t + "\n"


class CoderAgent(TextAgent):
    name = "coder"
    actions = tuple(_SYSTEMS)
    description = "Geração, explicação, revisão e proposta de código (somente texto)."

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        text, system = self.text_of(payload), _SYSTEMS[action]
        mode = payload.get("output_mode")
        if mode is None:
            return await self.provider.generate(self.model, text, system=system)
        if mode != "code_only" or action != "code_generate":
            raise ValueError("output_mode só aceita 'code_only' e somente em code_generate")
        strict = system + " Responda SOMENTE com o código, sem Markdown e sem explicações."
        try:
            return enforce_code_only(await self.provider.generate(self.model, text, system=strict))
        except CodeFormatError:  # segunda chance; se falhar de novo, o erro sobe
            return enforce_code_only(await self.provider.generate(self.model, text, system=strict))
