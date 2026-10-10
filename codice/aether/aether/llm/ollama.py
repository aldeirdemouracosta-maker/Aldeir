from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
from rich.console import Console

from aether.config import LLMConfig
from aether.llm.local import ensure_local_model
from aether.security import local_url

console = Console()


class OllamaClient:
    """Cliente simples e robusto para Ollama com suporte a tool calling."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = local_url(config.base_url)
        self.client = httpx.Client(timeout=120.0, trust_env=False, follow_redirects=False)
        self.last_response_metadata: dict[str, Any] = {}

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Faz uma chamada de chat.
        Retorna o message completo do assistant (com possível tool_calls).
        """
        ensure_local_model(self.client, self.base_url, self.config.model)
        self.last_response_metadata = {}
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if tools:
            payload["tools"] = tools

        try:
            resp = self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            self.last_response_metadata = {"done_reason": data.get("done_reason"),
                                           "done": data.get("done"),
                                           "eval_count": data.get("eval_count")}
            message = data.get("message", {})
            if not isinstance(message, dict):
                raise TypeError("Invalid Ollama message")
            return message
        except httpx.HTTPError as e:
            console.print(f"[red]Erro na chamada ao Ollama:[/red] {e}")
            raise

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Generator[str, None, None]:
        """Stream de texto (sem tool calling por enquanto)."""
        ensure_local_model(self.client, self.base_url, self.config.model)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

    def is_available(self) -> bool:
        try:
            ensure_local_model(self.client, self.base_url, self.config.model)
            resp = self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
