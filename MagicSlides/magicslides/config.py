"""Configurações do usuário (provedor de IA, chaves, fontes de imagem).

Salvas em %APPDATA%\\MagicSlides\\config.json no Windows e em
~/.config/magicslides/config.json no Linux/macOS. Variáveis de ambiente
(ANTHROPIC_API_KEY, OPENAI_API_KEY, PEXELS_API_KEY, UNSPLASH_ACCESS_KEY,
PIXABAY_API_KEY) são usadas quando o campo correspondente estiver vazio.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

SECRET_KEYS = ("anthropic_api_key", "openai_api_key", "pexels_api_key", "unsplash_access_key", "pixabay_api_key")
ENV_FALLBACK = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "pexels_api_key": "PEXELS_API_KEY",
    "unsplash_access_key": "UNSPLASH_ACCESS_KEY",
    "pixabay_api_key": "PIXABAY_API_KEY",
}
PROVIDERS = ("offline", "anthropic", "openai")
IMAGE_SOURCES = ("openverse", "wikimedia", "pexels", "unsplash", "pixabay")

DEFAULTS: dict[str, Any] = {
    "provider": "offline",
    "anthropic_api_key": "",
    "anthropic_model": "claude-opus-5",
    "anthropic_effort": "medium",
    # Qualquer servidor compatível com a API de chat da OpenAI:
    # Ollama (http://localhost:11434/v1), LM Studio (http://localhost:1234/v1),
    # llama.cpp server, OpenAI, Groq, OpenRouter...
    "openai_base_url": "http://localhost:11434/v1",
    "openai_api_key": "",
    "openai_model": "llama3.1",
    "image_sources": ["openverse", "wikimedia"],
    "pexels_api_key": "",
    "unsplash_access_key": "",
    "pixabay_api_key": "",
    "language": "Português do Brasil",
    "author": "",
}

_lock = threading.Lock()


def config_dir() -> Path:
    override = os.environ.get("MAGICSLIDES_HOME")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "MagicSlides"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MagicSlides"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "magicslides"


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict[str, Any]:
    data = dict(DEFAULTS)
    try:
        stored = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return _clean(data)


def effective(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Configuração com chaves vindas do ambiente quando não salvas."""
    data = dict(data or load())
    for key, env in ENV_FALLBACK.items():
        if not data.get(key):
            data[key] = os.environ.get(env, "")
    return data


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("provider") not in PROVIDERS:
        data["provider"] = "offline"
    sources = data.get("image_sources")
    if not isinstance(sources, list):
        sources = list(DEFAULTS["image_sources"])
    data["image_sources"] = [s for s in sources if s in IMAGE_SOURCES]
    for key, default in DEFAULTS.items():
        if isinstance(default, str) and not isinstance(data.get(key), str):
            data[key] = default
    return data


def save(update: dict[str, Any]) -> dict[str, Any]:
    """Mescla `update` na configuração salva. Chave secreta vazia ou
    ausente mantém o valor anterior; use "__clear__" para apagar."""
    with _lock:
        data = load()
        for key, value in (update or {}).items():
            if key not in DEFAULTS:
                continue
            if key in SECRET_KEYS:
                if value == "__clear__":
                    data[key] = ""
                elif isinstance(value, str) and value.strip():
                    data[key] = value.strip()
                continue
            data[key] = value
        data = _clean(data)
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return data


def public_view(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Versão segura para enviar ao navegador: chaves nunca saem do backend."""
    data = data or load()
    eff = effective(data)
    view = {k: v for k, v in data.items() if k not in SECRET_KEYS}
    for key in SECRET_KEYS:
        view[f"has_{key}"] = bool(eff.get(key))
        view[f"{key}_from_env"] = bool(not data.get(key) and eff.get(key))
    view["config_path"] = str(config_path())
    return view
