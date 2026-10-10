"""Thread-safe agent bridge; deliberately independent of the UI toolkit."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, TimeoutError
from queue import Queue
from threading import Lock
from typing import Any

from aether.agent import AetherAgent
from aether.agent.tools import ToolResult
from aether.config import AetherConfig


class AgentSession:
    def __init__(self, config: AetherConfig, *,
                 agent_factory: Callable[..., AetherAgent] = AetherAgent) -> None:
        self.config = config.model_copy(deep=True)
        self.config.agent.allow_unisolated_terminal = False
        self.factory = agent_factory
        self.agent: AetherAgent | None = None
        self.events: Queue[tuple[str, Any]] = Queue()
        self.pending_answer: Future[str] | None = None
        self.lock = Lock()
        self.running = False
        self.closed = False

    def _plan(self, content: str) -> None:
        self.events.put(("plan", content))

    def _tool(self, name: str, result: ToolResult) -> None:
        self.events.put(("tool", (name, result.output if result.success else result.error,
                                 result.success)))

    def _ask(self, question: str) -> str:
        answer: Future[str] = Future()
        with self.lock:
            if self.closed:
                return ""
            self.pending_answer = answer
        self.events.put(("question", (question, answer)))
        try:
            return answer.result(timeout=300)
        except (TimeoutError, CancelledError):
            return ""
        finally:
            with self.lock:
                answer.cancel()
                self.pending_answer = None

    def execute(self, task: str, skills: list[str]) -> str:
        with self.lock:
            if self.closed:
                raise RuntimeError("Sessão encerrada")
            if self.running:
                raise RuntimeError("Uma tarefa já está em execução")
            self.running = True
        try:
            if self.agent is None:
                self.agent = self.factory(self.config, ask_user=self._ask,
                                          on_plan=self._plan, on_tool_result=self._tool)
            return self.agent.run(task, skills=skills)
        finally:
            with self.lock:
                self.running = False
                if self.closed and self.agent is not None:
                    self.agent.close()
                    self.agent = None

    def reset(self) -> None:
        with self.lock:
            if self.running or self.closed:
                return
            if self.agent:
                self.agent.reset()

    def close(self) -> None:
        with self.lock:
            self.closed = True
            if self.pending_answer is not None:
                self.pending_answer.cancel()
            if self.agent is not None and not self.running:
                self.agent.close()
                self.agent = None
