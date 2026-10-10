from typing import Any

from .tools import ToolRegistry, get_default_tools

__all__ = ["AetherAgent", "ToolRegistry", "get_default_tools"]
def __getattr__(name: str) -> Any:
    if name == "AetherAgent":
        from .agent import AetherAgent
        return AetherAgent
    raise AttributeError(name)
