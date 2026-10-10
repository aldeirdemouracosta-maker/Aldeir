from typing import Any

__all__ = ["OllamaClient"]
def __getattr__(name: str) -> Any:
    if name == "OllamaClient":
        from .ollama import OllamaClient
        return OllamaClient
    raise AttributeError(name)
