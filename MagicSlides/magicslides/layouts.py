"""Motor de layouts: transforma um roteiro (outline) em slides prontos.

O roteiro é o que a IA (ou o modo offline) devolve:

    {"title": str, "subtitle": str, "slides": [
        {"layout": str, "title": str, "subtitle": str, "bullets": [str],
         "body": str, "quote": str, "quote_author": str,
         "stats": [{"value": str, "label": str}],
         "columns": [{"heading": str, "bullets": [str]}],
         "image_query": str, "notes": str}
    ]}
"""
from __future__ import annotations

import math
from typing import Any

from . import __version__
from .core import CANVAS_H, CANVAS_W, SCHEMA, uid
from .themes import get_theme, role_color

LAYOUTS = [
    "title", "section", "bullets", "image-right", "image-left",
    "two-column", "stats", "steps", "quote", "image-full", "closing",
]
IMAGE_LAYOUTS = {"image-right", "image-left", "image-full"}
PT_PER_UNIT = 960.0 / CANVAS_W  # 9.6pt por unidade do canvas
MAX_SLIDES = 40


# ---------------------------------------------------------------- roteiro ---

def _s(value: Any, limit: int = 400) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split()) if not isinstance(value, str) else value.strip()
    return text[:limit]


def _list(value: Any, limit: int = 6, size: int = 220) -> list[str]:
    if isinstance(value, str):
        value = [v for v in value.split("\n")]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = _s(item, size).lstrip("-•*· ").strip()
        if text:
            out.append(text)
    return out[:limit]


def normalize_outline(raw: Any, max_slides: int = MAX_SLIDES) -> dict[str, Any]:
    """Aceita qualquer JSON vindo de um modelo e devolve um roteiro seguro."""
    if not isinstance(raw, dict):
        raw = {}
    slides_in = raw.get("slides") if isinstance(raw.get("slides"), list) else []
    title = _s(raw.get("title"), 160) or "Apresentação"
    outline = {"title": title, "subtitle": _s(raw.get("subtitle"), 240), "slides": []}
    for item in slides_in:
        if not isinstance(item, dict):
            continue
        layout = _s(item.get("layout"), 30).lower()
        if layout not in LAYOUTS:
            layout = "bullets"
        stats = []
        for st in item.get("stats") or []:
            if isinstance(st, dict) and (_s(st.get("value")) or _s(st.get("label"))):
                stats.append({"value": _s(st.get("value"), 24), "label": _s(st.get("label"), 90)})
        columns = []
        for col in item.get("columns") or []:
            if isinstance(col, dict):
                columns.append({"heading": _s(col.get("heading"), 80), "bullets": _list(col.get("bullets"), 5, 160)})
        outline["slides"].append({
            "layout": layout,
            "title": _s(item.get("title"), 160),
            "subtitle": _s(item.get("subtitle"), 240),
            "bullets": _list(item.get("bullets")),
            "body": _s(item.get("body"), 700),
            "quote": _s(item.get("quote"), 400),
            "quote_author": _s(item.get("quote_author"), 120),
            "stats": stats[:4],
            "columns": columns[:2],
            "image_query": _s(item.get("image_query"), 120),
            "notes": _s(item.get("notes"), 2000),
        })
    if not outline["slides"] or outline["slides"][0]["layout"] != "title":
        outline["slides"].insert(0, {
            "layout": "title", "title": title, "subtitle": outline["subtitle"], "bullets": [], "body": "",
            "quote": "", "quote_author": "", "stats": [], "columns": [], "image_query": "", "notes": "",
        })
    outline["slides"] = outline["slides"][:max(1, min(max_slides, MAX_SLIDES))]
    return outline


# ----------------------------------------------------------- ajuste texto ---

def _char_w(bold: bool) -> float:
    return 0.6 if bold else 0.54


def text_height(text: str, w: float, fs: float, bullets: bool = False, bold: bool = False) -> float:
    """Altura estimada (em unidades do canvas) do texto numa caixa de largura w."""
    paragraphs = str(text).split("\n") or [""]
    usable = w * PT_PER_UNIT - (fs * 1.1 if bullets else 0)
    chars_per_line = max(4.0, usable / (fs * _char_w(bold)))
    lines = sum(max(1, math.ceil(len(p) / chars_per_line)) for p in paragraphs)
    gaps = (len(paragraphs) - 1) * fs * (0.45 if bullets else 0.2)
    return (lines * fs * 1.2 + gaps) / PT_PER_UNIT


def fit_font(text: str, w: float, h: float, max_fs: float, min_fs: float = 11, bullets: bool = False,
             bold: bool = False) -> int:
    """Maior tamanho de fonte (pt) em que o texto cabe na caixa (estimativa)."""
    fs = float(max_fs)
    while fs > min_fs and text_height(text, w, fs, bullets, bold) > h:
        fs -= 1
    return int(max(min_fs, fs))


# --------------------------------------------------------------- elementos ---

def _text(theme, role, x, y, w, h, text, max_fs, *, bold=False, align="left", heading=False,
          bullets=False, italic=False, min_fs=11, valign="top") -> dict[str, Any]:
    fs = fit_font(text, w, h, max_fs, min_fs, bullets, bold)
    return {
        "id": uid("text"), "type": "text", "role": role,
        "x": round(x, 3), "y": round(y, 3), "w": round(w, 3), "h": round(h, 3),
        "text": text, "fontSize": fs, "bold": bold, "italic": italic,
        "color": role_color(theme, role, theme["foreground"]), "align": align, "valign": valign,
        "font": theme.get("headingFont") if heading else theme.get("font"),
        "bullets": bullets,
    }


def _shape(theme, role, x, y, w, h, *, shape="rect", opacity=1.0, radius=0) -> dict[str, Any]:
    return {
        "id": uid("shape"), "type": "shape", "role": role, "shape": shape,
        "x": round(x, 3), "y": round(y, 3), "w": round(w, 3), "h": round(h, 3),
        "fill": role_color(theme, role, theme["accent"]), "stroke": None,
        "opacity": opacity, "radius": radius,
    }


def _image(x, y, w, h, query: str, alt: str) -> dict[str, Any]:
    return {
        "id": uid("image"), "type": "image", "x": x, "y": y, "w": w, "h": h,
        "src": "", "query": query, "alt": alt or query, "credit": "", "fit": "cover",
    }


def _bar(theme, x, y, w=6.0):
    return _shape(theme, "accent-fill", x, y, w, 0.8, radius=1)


def _heading(theme, x, y, w, max_h, title, max_fs) -> tuple[list[dict[str, Any]], float]:
    """Título + barra de destaque logo abaixo. Devolve (elementos, y livre)."""
    el = _text(theme, "title", x, y, w, max_h, title, max_fs, bold=True, heading=True)
    used = min(max_h, text_height(title, w, el["fontSize"], bold=True) + 0.4)
    el["h"] = round(used, 3)
    bar_y = y + used + 1.2
    return [el, _bar(theme, x, bar_y)], bar_y + 3.2


def _body_text(spec: dict[str, Any]) -> tuple[str, bool]:
    if spec["bullets"]:
        return "\n".join(spec["bullets"]), True
    return spec["body"], False


# ------------------------------------------------------------------ slides ---

def build_slide(spec: dict[str, Any], theme: dict[str, Any], topic: str = "") -> dict[str, Any]:
    layout = spec["layout"]
    els: list[dict[str, Any]] = []
    background = None
    query = spec["image_query"] or (f"{topic} {spec['title']}".strip() if layout in IMAGE_LAYOUTS else "")
    title = spec["title"]
    body, is_bullets = _body_text(spec)

    if layout in ("title", "closing"):
        has_image = bool(spec["image_query"]) and layout == "title"
        if has_image:
            els.append(_image(52, 0, 48, CANVAS_H, query, title))
            tx, tw = 6, 42
        else:
            els.append(_shape(theme, "accent-fill", 70, -12, 44, 44 * 1.0, shape="ellipse", opacity=0.16))
            els.append(_shape(theme, "accent-fill", 82, 36, 22, 22, shape="ellipse", opacity=0.10))
            tx, tw = 8, 70
        align = "left"
        els.append(_bar(theme, tx, 17))
        els.append(_text(theme, "title", tx, 20, tw, 17, title, 54 if not has_image else 44, bold=True, heading=True, align=align))
        sub = spec["subtitle"] or body
        if sub:
            els.append(_text(theme, "muted", tx, 38.5, tw, 11, sub, 22, align=align))

    elif layout == "section":
        background = theme["accent"]
        els.append(_shape(theme, "on-accent", 8, 20, 8, 0.8, radius=1))
        els.append(_text(theme, "on-accent", 8, 22.5, 84, 14, title, 50, bold=True, heading=True))
        sub = spec["subtitle"] or body
        if sub:
            els.append(_text(theme, "on-accent", 8, 37, 70, 9, sub, 22))

    elif layout in ("image-right", "image-left"):
        right = layout == "image-right"
        ix, tx = (54, 6) if right else (0, 50)
        els.append(_image(ix, 0, 46, CANVAS_H, query, title))
        head, top = _heading(theme, tx, 6, 44, 16, title, 34)
        els += head
        if body:
            els.append(_text(theme, "body", tx, top, 44, 52 - top, body, 22, bullets=is_bullets))

    elif layout == "image-full":
        els.append(_image(0, 0, CANVAS_W, CANVAS_H, query, title))
        els.append(_shape(theme, "overlay", 0, 0, CANVAS_W, CANVAS_H, opacity=0.5))
        els.append(_text(theme, "on-image", 6, 27, 84, 13, title, 44, bold=True, heading=True, valign="bottom"))
        if body:
            els.append(_text(theme, "on-image", 6, 41, 80, 11, body, 20, bullets=is_bullets))

    elif layout == "two-column":
        cols = spec["columns"] or []
        if len(cols) < 2:
            half = max(1, math.ceil(len(spec["bullets"]) / 2))
            cols = [{"heading": "", "bullets": spec["bullets"][:half]}, {"heading": "", "bullets": spec["bullets"][half:]}]
        head, ytop = _heading(theme, 6, 5, 88, 11, title, 34)
        els += head
        for i, col in enumerate(cols[:2]):
            cx = 6 + i * 45
            els.append(_shape(theme, "surface-fill", cx, ytop, 43, 52 - ytop, radius=2.5))
            top = ytop + 2.5
            if col["heading"]:
                els.append(_text(theme, "accent", cx + 2.5, top, 38, 6, col["heading"], 22, bold=True, heading=True))
                top += 7.5
            if col["bullets"]:
                els.append(_text(theme, "body", cx + 2.5, top, 38, 52 - top - 2, "\n".join(col["bullets"]), 19, bullets=True))

    elif layout == "stats":
        stats = spec["stats"] or [{"value": b.split(" ")[0], "label": " ".join(b.split(" ")[1:])} for b in spec["bullets"][:4]]
        stats = stats[:4] or [{"value": "—", "label": ""}]
        head, _ = _heading(theme, 6, 5, 88, 11, title, 34)
        els += head
        n = len(stats)
        gap = 3.0
        cw = (88 - gap * (n - 1)) / n
        for i, st in enumerate(stats):
            cx = 6 + i * (cw + gap)
            els.append(_shape(theme, "surface-fill", cx, 21, cw, 19, radius=2.5))
            els.append(_text(theme, "accent", cx + 1.5, 23, cw - 3, 9, st["value"], 44, bold=True, heading=True, align="center"))
            if st["label"]:
                els.append(_text(theme, "muted", cx + 1.5, 32.5, cw - 3, 6.5, st["label"], 16, align="center"))
        if spec["body"]:
            els.append(_text(theme, "body", 6, 43, 88, 9, spec["body"], 18))

    elif layout == "steps":
        steps = spec["bullets"][:5] or [spec["body"] or ""]
        head, _ = _heading(theme, 6, 5, 88, 11, title, 34)
        els += head
        n = len(steps)
        cw = 88 / n
        els.append(_shape(theme, "surface-fill", 6 + cw / 2, 26.2, 88 - cw, 0.6))
        for i, step in enumerate(steps):
            cx = 6 + i * cw
            circle_x = cx + cw / 2 - 3.5
            els.append(_shape(theme, "accent-fill", circle_x, 23, 7, 7, shape="ellipse"))
            els.append(_text(theme, "on-accent", circle_x, 24.3, 7, 4.5, str(i + 1), 22, bold=True, align="center"))
            els.append(_text(theme, "body", cx + 1, 33, cw - 2, 19, step, 18, align="center"))

    elif layout == "quote":
        quote = spec["quote"] or spec["body"] or title
        els.append(_text(theme, "accent", 6, 3, 14, 18, "“", 140, bold=True, heading=True))
        els.append(_text(theme, "title", 12, 16, 76, 24, quote, 34, italic=True, heading=True))
        author = spec["quote_author"]
        if author:
            els.append(_text(theme, "muted", 12, 41.5, 76, 6, f"— {author}", 18))
        if spec["title"] and spec["title"] != quote:
            els.append(_text(theme, "muted", 12, 47.5, 76, 5, spec["title"], 14))

    else:  # bullets
        head, top = _heading(theme, 6, 6, 88, 12, title, 38)
        els += head
        if body:
            els.append(_text(theme, "body", 6, top, 88, 52 - top, body, 26, bullets=is_bullets))

    return {
        "id": uid("slide"),
        "name": title or layout,
        "layout": layout,
        "background": background,
        "bgRole": "accent" if background else None,
        "notes": spec.get("notes", ""),
        "elements": els,
    }


def build_credits_slide(credits: list[str], theme: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(credits[:14])
    els, top = _heading(theme, 6, 5, 88, 10, "Créditos das imagens", 30)
    els.append(_text(theme, "muted", 6, top, 88, 53 - top, text, 14, bullets=True, min_fs=8))
    return {"id": uid("slide"), "name": "Créditos das imagens", "layout": "credits", "background": None,
            "bgRole": None, "notes": "", "elements": els}


def build_presentation(outline: dict[str, Any], theme_id: str | None, author: str = "") -> dict[str, Any]:
    theme = get_theme(theme_id)
    topic = outline.get("title", "")
    return {
        "schema": SCHEMA,
        "version": __version__,
        "meta": {"title": outline.get("title") or "Apresentação", "author": author},
        "canvas": {"ratio": "16:9", "width": CANVAS_W, "height": CANVAS_H},
        "theme": theme,
        "slides": [build_slide(spec, theme, topic) for spec in outline["slides"]],
    }
