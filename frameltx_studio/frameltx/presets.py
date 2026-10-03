"""Presets prontos e estilos visuais.

Para adicionar um preset, basta incluir um ``Preset`` em ``PRESETS``; ele aparece
automaticamente na interface. Presets do usuário podem ser colocados em
``presets_custom.json`` (mesma estrutura dos campos abaixo).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

BASE_NEGATIVE = (
    "blurry, low quality, distorted, deformed, watermark, text, logo, "
    "jitter, flicker, extra limbs, bad anatomy"
)


@dataclass(frozen=True)
class Preset:
    name: str
    # Texto adicionado ao prompt do usuário (descreve o tipo de movimento).
    prompt_suffix: str
    # Prompt usado se o usuário deixar o campo em branco.
    default_prompt: str
    negative: str = BASE_NEGATIVE
    recommended_mode: str = "framepack"
    recommended_style: str = "Realista"
    # Se definido, o vídeo final é reamostrado para este FPS (ex.: efeito stop-motion).
    post_fps: int | None = None
    # Intensidade de movimento no FramePack (guidance destilado).
    motion_guidance: float = 10.0


@dataclass(frozen=True)
class Style:
    name: str
    prompt_suffix: str
    negative_extra: str = ""


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        Preset(
            "Livre", "", "", recommended_mode="framepack",
        ),
        Preset(
            "Pessoa falando",
            "the person talks naturally to the camera, subtle head movements, "
            "natural blinking, expressive face, lips moving in sync with speech",
            "A person speaking enthusiastically to the camera",
            recommended_mode="ltx", motion_guidance=9.0,
        ),
        Preset(
            "Produto girando",
            "the product rotates slowly 360 degrees on a turntable, studio lighting, "
            "clean background, smooth constant rotation, commercial product shot",
            "A product rotating on a turntable",
            recommended_style="Comercial",
        ),
        Preset(
            "Cena cinematográfica",
            "slow cinematic dolly camera movement, shallow depth of field, "
            "dramatic lighting, volumetric light, film grain",
            "An epic cinematic establishing shot",
            recommended_mode="combinado", recommended_style="Cinematográfico",
        ),
        Preset(
            "Stop-motion style",
            "stop-motion animation, handcrafted claymation look, choppy charming movement",
            "A clay character walking across a tiny handmade set",
            recommended_style="Stop-motion", post_fps=12, motion_guidance=11.0,
        ),
        Preset(
            "Dança",
            "the person dances energetically with fluid full body movement, rhythmic motion",
            "A person dancing",
            motion_guidance=11.0,
        ),
        Preset(
            "Paisagem timelapse",
            "timelapse, clouds moving fast across the sky, light changing, gentle camera push in",
            "A mountain landscape at sunset",
            recommended_style="Cinematográfico",
        ),
    )
}

STYLES: dict[str, Style] = {
    s.name: s
    for s in (
        Style("Realista", "photorealistic, natural colors, high detail"),
        Style("Cinematográfico", "cinematic color grading, anamorphic look, 35mm film", "flat lighting"),
        Style("Comercial", "bright clean commercial look, crisp, vibrant colors"),
        Style("Anime", "anime style, cel shading, vibrant colors", "photorealistic"),
        Style("Stop-motion", "claymation, handmade miniature set, tactile textures", "smooth cgi"),
        Style("Vintage", "vintage 16mm film, warm tones, light leaks, grain"),
    )
}

CUSTOM_PRESETS_FILE = Path(__file__).resolve().parent.parent / "presets_custom.json"


def load_custom_presets(path: Path = CUSTOM_PRESETS_FILE) -> None:
    """Mescla presets do usuário (JSON: lista de objetos Preset) aos padrões."""
    if not path.exists():
        return
    try:
        for item in json.loads(path.read_text(encoding="utf-8")):
            preset = Preset(**item)
            PRESETS[preset.name] = preset
            log.info("Preset personalizado carregado: %s", preset.name)
    except (json.JSONDecodeError, TypeError) as exc:
        log.error("presets_custom.json inválido: %s", exc)


def build_prompts(user_prompt: str, preset_name: str, style_name: str) -> tuple[str, str]:
    """Combina prompt do usuário + preset + estilo. Retorna (positivo, negativo)."""
    preset = PRESETS.get(preset_name, PRESETS["Livre"])
    style = STYLES.get(style_name, STYLES["Realista"])
    base = user_prompt.strip() or preset.default_prompt or "A beautiful scene with gentle motion"
    positive = ", ".join(p for p in (base, preset.prompt_suffix, style.prompt_suffix) if p)
    negative = ", ".join(n for n in (preset.negative, style.negative_extra) if n)
    return positive, negative


def preset_as_dict(name: str) -> dict:
    return asdict(PRESETS[name])
