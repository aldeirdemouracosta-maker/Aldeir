"""Tipos de dados compartilhados."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TaskResult:
    agent: str
    action: str
    ok: bool
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SwarmError(Exception):
    """Erro esperado e tratável da aplicação."""


class RegistryError(SwarmError):
    pass


class RouteError(SwarmError):
    pass


class ProviderError(SwarmError):
    pass


class UnavailableError(SwarmError):
    """Agente ou dependência opcional indisponível (pesos ou pacotes ausentes)."""


class OutputError(SwarmError):
    """Saída de modelo ou plano inválidos (formato), distinta de erro de infraestrutura."""
