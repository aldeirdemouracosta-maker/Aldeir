from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aether.security import local_url


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, validate_default=True)

    @field_validator("model", check_fields=False)
    @classmethod
    def local_model(cls, value: str) -> str:
        if not value.strip() or "cloud" in value.lower():
            raise ValueError("Cloud models are disabled")
        return value



class EmbedderConfig(StrictModel):
    model: str = "nomic-embed-text"
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://localhost:11434"
    dimension: int = Field(default=768, ge=1)
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)

    _local = field_validator("base_url")(local_url)


class LLMConfig(StrictModel):
    model: str = "qwen3:8b"
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://localhost:11434"
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=8192, ge=1, le=32768)

    _local = field_validator("base_url")(local_url)


class IndexerConfig(StrictModel):
    chunk_size: int = Field(default=1200, ge=1)
    chunk_overlap: int = Field(default=200, ge=0)
    include_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
            ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
            ".kt", ".scala", ".md", ".mdx", ".txt", ".json", ".yaml",
            ".yml", ".toml", ".html", ".css", ".scss", ".vue", ".svelte"
        ]
    )
    exclude_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", ".nuxt", "target", "vendor",
            ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache"
        ]
    )
    max_file_size_kb: int = Field(default=500, ge=1)


    @model_validator(mode="after")
    def valid_overlap(self) -> "IndexerConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap deve ser menor que chunk_size")
        return self


class VectorStoreConfig(StrictModel):
    path: str = ".aether/lancedb"
    table_name: str = "codebase"


class AgentConfig(StrictModel):
    max_iterations: int = Field(default=25, ge=1, le=100)
    max_tool_calls: int = Field(default=8, ge=1, le=32)
    max_tool_steps: int = Field(default=50, ge=1, le=500)
    max_tool_failures: int = Field(default=3, ge=1)
    max_context_chars: int = Field(default=48000, ge=2048)
    max_tool_output_chars: int = Field(default=12000, ge=128)
    max_response_chars: int = Field(default=12000, ge=128)
    allow_unisolated_terminal: bool = False
    terminal_timeout: int = Field(default=30, ge=1, le=120)
    require_plan_approval: bool = False
    verbose: bool = True


class CacheConfig(StrictModel):
    enabled: bool = True
    path: str = ".aether/embeddings.sqlite3"
    max_bytes: int = Field(default=134217728, ge=65536)


class SkillsConfig(StrictModel):
    max_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_skills: int = Field(default=100, ge=1, le=1000)
    max_selected: int = Field(default=5, ge=1, le=20)


class AetherConfig(StrictModel):
    project_root: Path = Field(default_factory=Path.cwd)
    embedder: EmbedderConfig = Field(default_factory=lambda: EmbedderConfig())
    llm: LLMConfig = Field(default_factory=lambda: LLMConfig())
    indexer: IndexerConfig = Field(default_factory=lambda: IndexerConfig())
    vectorstore: VectorStoreConfig = Field(default_factory=lambda: VectorStoreConfig())
    agent: AgentConfig = Field(default_factory=lambda: AgentConfig())
    cache: CacheConfig = Field(default_factory=lambda: CacheConfig())
    skills: SkillsConfig = Field(default_factory=lambda: SkillsConfig())

    @classmethod
    def load(cls, path: str | Path | None = None) -> "AetherConfig":
        config_path = Path(path) if path else Path("aether.yaml")
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self, path: str | Path | None = None) -> None:
        config_path = Path(path) if path else Path("aether.yaml")
        data = self.model_dump(mode="json")
        # Convert Path to str for YAML
        data["project_root"] = str(self.project_root)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
