"""Machine-readable completion state, independent of assistant prose."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TaskOutcome:
    status: Literal["completed", "incomplete", "failed"]
    code: str
    reason: str


class AgentInterrupted(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
