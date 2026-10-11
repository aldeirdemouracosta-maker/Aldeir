"""Slot de modelo: garante no máximo um modelo pesado residente por worker (GPU)."""
from __future__ import annotations

import threading
from typing import Callable, Protocol


class Backend(Protocol):
    def load(self, model: str) -> None: ...
    def unload(self, model: str) -> None: ...


class MockBackend:
    """Backend simulado da Fase 2: apenas contabiliza carga/descarga e o pico de residentes."""

    def __init__(self) -> None:
        self.resident: set[str] = set()
        self.peak = 0

    def load(self, model: str) -> None:
        self.resident.add(model)
        self.peak = max(self.peak, len(self.resident))

    def unload(self, model: str) -> None:
        self.resident.discard(model)


class ModelSlot:
    """Serializa o acesso à GPU: troca de modelo = descarrega o atual, depois carrega o novo."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.loaded: str | None = None
        self.history: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def run(self, model: str, fn: Callable[[str], object]) -> object:
        with self._lock:
            if self.loaded != model:
                if self.loaded is not None:
                    self.backend.unload(self.loaded)
                    self.history.append(("unload", self.loaded))
                    self.loaded = None
                self.backend.load(model)
                self.loaded = model
                self.history.append(("load", model))
            return fn(model)

    def unload(self) -> None:
        with self._lock:
            if self.loaded is not None:
                self.backend.unload(self.loaded)
                self.history.append(("unload", self.loaded))
                self.loaded = None
