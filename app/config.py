"""Configuração: valores padrão seguros (loopback) com override por ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.models import SwarmError

# Configurações e suítes de avaliação vivem DENTRO do pacote (funcionam em qualquer instalação).
# SWARM_CONFIG_DIR aponta outra pasta com agents.yaml, models.yaml e evals/.
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = PACKAGE_DIR / "configs"
DEFAULT_AGENTS_FILE = DEFAULT_CONFIG_DIR / "agents.yaml"


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
    queue_timeout: float = 60.0
    headroom_mb: int = 1024
    models_file: Path = DEFAULT_CONFIG_DIR / "models.yaml"
    evals_dir: Path = PACKAGE_DIR / "evals"
    models_dir: Path = Path.home() / ".swarm" / "models"
    coord_dir: Path | None = None  # None = sem coordenação entre processos
    coord_capacity: int = 1
    allowed_hosts: tuple[str, ...] = field(default=("127.0.0.1", "localhost"))

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        cfg = Path(e["SWARM_CONFIG_DIR"]) if e.get("SWARM_CONFIG_DIR") else None
        return cls(
            **({"agents_file": cfg / "agents.yaml", "models_file": cfg / "models.yaml",
                "evals_dir": cfg / "evals"} if cfg else {}),
            host=e.get("SWARM_HOST", cls.host),
            port=int(e.get("SWARM_PORT", cls.port)),
            provider=e.get("SWARM_PROVIDER", cls.provider),
            provider_url=e.get("SWARM_PROVIDER_URL", cls.provider_url),
            media_dir=Path(e["SWARM_MEDIA"]) if e.get("SWARM_MEDIA") else Path.home() / ".swarm" / "media",
            embed_model=e.get("SWARM_EMBED_MODEL", cls.embed_model),
            max_concurrent=int(e.get("SWARM_MAX_CONCURRENT", cls.max_concurrent)),
            max_queue=int(e.get("SWARM_MAX_QUEUE", cls.max_queue)),
            job_timeout=float(e.get("SWARM_JOB_TIMEOUT", cls.job_timeout)),
            queue_timeout=float(e.get("SWARM_QUEUE_TIMEOUT", cls.queue_timeout)),
            headroom_mb=int(e.get("SWARM_HEADROOM_MB", cls.headroom_mb)),
            models_dir=Path(e["SWARM_MODELS_DIR"]) if e.get("SWARM_MODELS_DIR") else cls.models_dir,
            coord_dir=Path(e["SWARM_COORD_DIR"]) if e.get("SWARM_COORD_DIR") else None,
            request_timeout=float(e.get("SWARM_TIMEOUT", cls.request_timeout)),
            state_path=Path(e["SWARM_STATE"]) if e.get("SWARM_STATE") else Path.home() / ".swarm" / "state.db",
        )


class ConfigError(SwarmError):
    pass


def load_agent_config(path: Path) -> dict[str, dict]:
    """Lê agents.yaml. Arquivo ausente é erro: configuração vazia deixaria agentes sem modelo, em silêncio."""
    if not path.is_file():
        raise ConfigError(f"configuração ausente: {path} (instale com `pip install -e .` ou defina SWARM_CONFIG_DIR)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("agents", {})
