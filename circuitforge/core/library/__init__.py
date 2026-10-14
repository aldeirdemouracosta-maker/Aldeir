from .base import CATEGORIES, HELPERS, REGISTRY, CircuitDef, Lesson, Param, by_category, get
from . import (  # noqa: F401  (registro dos circuitos)
    basicos, fontes, computador, ia, audio, guitarra, solar, veiculos, radio_tv, antenas,
)

__all__ = ["CATEGORIES", "HELPERS", "REGISTRY", "CircuitDef", "Lesson", "Param",
           "by_category", "get", "list_example_circuits", "get_builder"]


def list_example_circuits():
    return {c.id: c.name for c in REGISTRY.values()}


def get_builder(circuit_id: str):
    return REGISTRY.get(circuit_id)
