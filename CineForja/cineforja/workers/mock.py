"""Despacho de tarefas da Fase 2.

Com CINEFORJA_WORKERS definido, delega aos workers HTTP; sem ele, simula em processo.
"""
from .client import dispatch


def run(task_type: str, what: str) -> str:
    return dispatch(task_type, what)


def score_shot(index: int, attempt: int) -> float:
    """Pontuação determinística: o shot 1 falha na primeira tentativa (testa regeneração)."""
    return 0.5 if (index == 1 and attempt == 1) else 0.9
