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
    state_path: Path | None = None  # None = só em memória
    media_dir: Path | None = None  # None = diretório temporário (não persiste)
    embed_model: str = "nomic-embed-text:latest"
    max_concurrent: int = 2
    max_queue: int = 16
    job_timeout: float = 120.0
    headroom_mb: int = 1024
    coord_dir: Path | None = None  # None = sem coordenação entre processos
    coord_capacity: int = 1
    allowed_hosts: tuple[str, ...] = field(default=("127.0.0.1", "localhost", "testserver"))

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            host=e.get("SWARM_HOST", cls.host),
            port=int(e.get("SWARM_PORT", cls.port)),
            provider=e.get("SWARM_PROVIDER", cls.provider),
            provider_url=e.get("SWARM_PROVIDER_URL", cls.provider_url),
            media_dir=Path(e["SWARM_MEDIA"]) if e.get("SWARM_MEDIA") else Path.home() / ".swarm" / "media",
            embed_model=e.get("SWARM_EMBED_MODEL", cls.embed_model),
            max_concurrent=int(e.get("SWARM_MAX_CONCURRENT", cls.max_concurrent)),
            max_queue=int(e.get("SWARM_MAX_QUEUE", cls.max_queue)),
            job_timeout=float(e.get("SWARM_JOB_TIMEOUT", cls.job_timeout)),
            headroom_mb=int(e.get("SWARM_HEADROOM_MB", cls.headroom_mb)),
            coord_dir=Path(e["SWARM_COORD_DIR"]) if e.get("SWARM_COORD_DIR") else None,
            request_timeout=float(e.get("SWARM_TIMEOUT", cls.request_timeout)),
            state_path=Path(e["SWARM_STATE"]) if e.get("SWARM_STATE") else Path.home() / ".swarm" / "state.db",
        )


def load_agent_config(path: Path) -> dict[str, dict]:
    """Lê configs/agents.yaml. Arquivo ausente significa configuração vazia."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("agents", {})
