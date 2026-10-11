"""Workers simulados da Fase 1: nenhum modelo real é carregado.

Cada função registra a GPU escolhida por choose_worker(), para validar o roteamento.
Na Fase 2/3 estas funções serão substituídas por chamadas aos workers reais.
"""
from .router import choose_worker


def run(task_type: str, what: str) -> str:
    return f"[{choose_worker(task_type)}] {what}"


def score_shot(index: int, attempt: int) -> float:
    """Pontuação determinística: o shot 1 falha na primeira tentativa (testa regeneração)."""
    return 0.5 if (index == 1 and attempt == 1) else 0.9
