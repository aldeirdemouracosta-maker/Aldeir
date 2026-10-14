"""Configuração: valores padrão seguros (loopback) com override por ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_AGENTS_FILE = Path(__file__).resolve().parent.parent / "configs" / "agents.yaml"


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    provider: str = "ollama"  # ollama | local_compatible
    provider_url: str = "http://127.0.0.1:11434"
    request_timeout: float = 120.0
    agents_file: Path = DEFAULT_AGENTS_FILE
    allowed_hosts: tuple[str, ...] = field(default=("127.0.0.1", "localhost", "testserver"))

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            host=e.get("SWARM_HOST", cls.host),
            port=int(e.get("SWARM_PORT", cls.port)),
            provider=e.get("SWARM_PROVIDER", cls.provider),
            provider_url=e.get("SWARM_PROVIDER_URL", cls.provider_url),
            request_timeout=float(e.get("SWARM_TIMEOUT", cls.request_timeout)),
        )


def load_agent_config(path: Path) -> dict[str, dict]:
    """Lê configs/agents.yaml. Arquivo ausente significa configuração vazia."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("agents", {})
