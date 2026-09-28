"""Formato canônico de apresentação do MagicSlides.

`presentation.json` é a fonte da verdade: editor, gerador com IA, exportação
PPTX e HTML leem e escrevem este mesmo formato.

Coordenadas: o slide mede 100 x 56.25 unidades (16:9). O tamanho de fonte é
em pontos de um slide de 960pt de largura (13.333in), igual ao PowerPoint.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from . import __version__
from .themes import DEFAULT_THEME, get_theme

SCHEMA = "magicslides.presentation"
LEGACY_SCHEMAS = {"gamma-livre.presentation"}
CANVAS_W = 100.0
CANVAS_H = 56.25

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ELEMENT_TYPES = {"text", "shape", "image"}


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def default_presentation() -> dict[str, Any]:
    theme = get_theme(DEFAULT_THEME)
    return {
        "schema": SCHEMA,
        "version": __version__,
        "meta": {"title": "Nova apresentação", "author": ""},
        "canvas": {"ratio": "16:9", "width": CANVAS_W, "height": CANVAS_H},
        "theme": theme,
        "slides": [default_slide("Slide 1", theme)],
    }


def default_slide(title: str = "Novo slide", theme: dict[str, Any] | None = None) -> dict[str, Any]:
    theme = theme or get_theme(DEFAULT_THEME)
    return {
        "id": uid("slide"),
        "name": title,
        "layout": "blank",
        "background": None,
        "notes": "",
        "elements": [
            {
                "id": uid("text"), "type": "text", "role": "title",
                "x": 8, "y": 8, "w": 84, "h": 12,
                "text": title, "fontSize": 36, "bold": True,
                "color": theme["foreground"], "align": "left",
            },
            {
                "id": uid("text"), "type": "text", "role": "body",
                "x": 8, "y": 24, "w": 84, "h": 22,
                "text": "Clique duas vezes no texto para editar. Arraste os blocos para reorganizar o slide.",
                "fontSize": 20, "bold": False,
                "color": theme["muted"], "align": "left",
            },
        ],
    }


def validate_presentation(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["A apresentação precisa ser um objeto JSON."]
    if data.get("schema") != SCHEMA:
        errors.append("schema inválido")
    if not isinstance(data.get("version"), str):
        errors.append("version ausente ou inválida")
    theme = data.get("theme")
    if not isinstance(theme, dict):
        errors.append("theme ausente")
    else:
        for key in ("background", "foreground", "accent"):
            if not isinstance(theme.get(key), str) or not HEX.match(theme[key]):
                errors.append(f"theme.{key} deve usar #RRGGBB")
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides precisa conter ao menos um slide")
        return errors
    slide_ids: set[str] = set()
    element_ids: set[str] = set()
    for si, slide in enumerate(slides):
        if not isinstance(slide, dict):
            errors.append(f"slides[{si}] inválido")
            continue
        sid = slide.get("id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"slides[{si}].id inválido")
        elif sid in slide_ids:
            errors.append(f"slides[{si}].id duplicado")
        else:
            slide_ids.add(sid)
        bg = slide.get("background")
        if bg is not None and (not isinstance(bg, str) or not HEX.match(bg)):
            errors.append(f"slides[{si}].background deve usar #RRGGBB ou null")
        elems = slide.get("elements")
        if not isinstance(elems, list):
            errors.append(f"slides[{si}].elements inválido")
            continue
        for ei, el in enumerate(elems):
            where = f"slides[{si}].elements[{ei}]"
            if not isinstance(el, dict):
                errors.append(f"{where} inválido")
                continue
            eid = el.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{where}.id inválido")
            elif eid in element_ids:
                errors.append(f"element id duplicado: {eid}")
            else:
                element_ids.add(eid)
            if el.get("type") not in ELEMENT_TYPES:
                errors.append(f"{where}.type inválido")
            for key in ("x", "y", "w", "h"):
                if not isinstance(el.get(key), (int, float)) or isinstance(el.get(key), bool):
                    errors.append(f"{where}.{key} inválido")
            if isinstance(el.get("x"), (int, float)) and not -CANVAS_W <= el["x"] <= CANVAS_W:
                errors.append(f"{where}.x fora do canvas")
            if isinstance(el.get("y"), (int, float)) and not -CANVAS_H <= el["y"] <= CANVAS_H:
                errors.append(f"{where}.y fora do canvas")
            if el.get("type") == "image":
                src = el.get("src", "")
                if src and not (isinstance(src, str) and src.startswith("data:image/")):
                    errors.append(f"{where}.src precisa ser uma imagem embutida (data URL)")
    return errors


def normalize_presentation(data: Any) -> Any:
    """Completa campos ausentes e migra projetos do Gamma Livre 0.1."""
    if not isinstance(data, dict):
        return data
    result = copy.deepcopy(data)
    if result.get("schema") in LEGACY_SCHEMAS or "schema" not in result:
        result["schema"] = SCHEMA
    result.setdefault("version", __version__)
    if not isinstance(result.get("meta"), dict):
        result["meta"] = {"title": "Apresentação", "author": ""}
    result.setdefault("canvas", {"ratio": "16:9", "width": CANVAS_W, "height": CANVAS_H})
    theme = result.get("theme")
    base = get_theme(DEFAULT_THEME)
    if isinstance(theme, dict):
        for key, value in base.items():
            theme.setdefault(key, value)
    else:
        result["theme"] = base
    if not isinstance(result.get("slides"), list) or not result["slides"]:
        result["slides"] = [default_slide("Slide 1", result["theme"])]
    for slide in result["slides"]:
        if isinstance(slide, dict):
            slide.setdefault("notes", "")
            slide.setdefault("layout", "blank")
            slide.setdefault("background", None)
    return result


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
