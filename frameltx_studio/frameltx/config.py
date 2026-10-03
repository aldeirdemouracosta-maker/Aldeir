"""Configuração central do FrameLTX Studio.

A ordem de precedência é: valores padrão < ``config.json`` < variáveis de ambiente.
Assim o usuário comum não precisa mexer em nada, e quem quiser customizar
(nomes de modelos, URL do ComfyUI, pasta de saída) tem um único lugar para isso.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_DIR / "config.json"


@dataclass
class ModelNames:
    """Nomes de arquivos de modelos, exatamente como aparecem nas pastas do ComfyUI."""

    # FramePack (pasta ComfyUI/models/diffusion_models)
    framepack: str = "FramePackI2V_HY_fp8_e4m3fn.safetensors"
    # Encoders de texto do HunyuanVideo (pasta models/text_encoders)
    framepack_clip_l: str = "clip_l.safetensors"
    framepack_llama: str = "llava_llama3_fp8_scaled.safetensors"
    # Encoder de visão (pasta models/clip_vision)
    framepack_clip_vision: str = "sigclip_vision_patch14_384.safetensors"
    # VAE do HunyuanVideo (pasta models/vae)
    framepack_vae: str = "hunyuan_video_vae_bf16.safetensors"
    # LTX-2 destilado em FP8 (pasta models/checkpoints) — contém VAE de vídeo e áudio
    ltx_checkpoint: str = "ltx-2-19b-distilled-fp8.safetensors"
    # Encoder de texto Gemma usado pelo LTX-2 (pasta models/text_encoders)
    ltx_text_encoder: str = "gemma_3_12B_it_fp8_scaled.safetensors"


@dataclass
class AppConfig:
    comfy_url: str = "http://127.0.0.1:8188"
    output_dir: Path = APP_DIR / "outputs"
    workflows_dir: Path = APP_DIR / "workflows"
    # Tempo máximo (s) de espera por uma única execução no ComfyUI.
    comfy_timeout: int = 60 * 60
    # Resolução final de exportação (9:16). Os modelos geram em resolução menor
    # e o ffmpeg faz o upscale para o formato das redes sociais.
    export_width: int = 1080
    export_height: int = 1920
    # Força um perfil de qualidade (baixo/medio/alto/ultra). Vazio = automático.
    force_profile: str = ""
    # Modo demonstração: não usa ComfyUI, gera vídeos sintéticos com ffmpeg.
    demo_mode: bool = False
    server_host: str = "127.0.0.1"
    server_port: int = 7860
    models: ModelNames = field(default_factory=ModelNames)


_ENV_MAP = {
    "COMFYUI_URL": "comfy_url",
    "FRAMELTX_OUTPUT_DIR": "output_dir",
    "FRAMELTX_WORKFLOWS_DIR": "workflows_dir",
    "FRAMELTX_PROFILE": "force_profile",
    "FRAMELTX_DEMO": "demo_mode",
    "FRAMELTX_HOST": "server_host",
    "FRAMELTX_PORT": "server_port",
}


def _coerce(value: object, current: object) -> object:
    """Converte ``value`` para o tipo do valor atual do campo."""
    if isinstance(current, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}
    if isinstance(current, int):
        return int(value)
    if isinstance(current, Path):
        return Path(str(value)).expanduser()
    return value


def _apply_overrides(cfg: AppConfig, data: dict) -> None:
    valid = {f.name for f in fields(AppConfig)}
    for key, value in data.items():
        if key == "models" and isinstance(value, dict):
            for mkey, mval in value.items():
                if hasattr(cfg.models, mkey):
                    setattr(cfg.models, mkey, str(mval))
                else:
                    log.warning("config.json: modelo desconhecido '%s' ignorado", mkey)
        elif key in valid:
            setattr(cfg, key, _coerce(value, getattr(cfg, key)))
        else:
            log.warning("config.json: chave desconhecida '%s' ignorada", key)


def load_config(path: Path | None = None) -> AppConfig:
    """Carrega a configuração combinando padrões, arquivo JSON e ambiente."""
    cfg = AppConfig()
    path = path or CONFIG_FILE
    if path.exists():
        try:
            _apply_overrides(cfg, json.loads(path.read_text(encoding="utf-8")))
            log.info("Configuração carregada de %s", path)
        except (json.JSONDecodeError, ValueError) as exc:
            log.error("config.json inválido (%s) — usando valores padrão", exc)
    env_overrides = {attr: os.environ[env] for env, attr in _ENV_MAP.items() if env in os.environ}
    _apply_overrides(cfg, env_overrides)
    cfg.comfy_url = cfg.comfy_url.rstrip("/")
    # Caminhos relativos são relativos à pasta do app, não ao diretório atual.
    cfg.output_dir = cfg.output_dir if cfg.output_dir.is_absolute() else APP_DIR / cfg.output_dir
    cfg.workflows_dir = cfg.workflows_dir if cfg.workflows_dir.is_absolute() else APP_DIR / cfg.workflows_dir
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    return cfg
