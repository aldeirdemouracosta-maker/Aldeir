"""Temas prontos. Cada elemento gerado guarda um `role` para poder ser
recolorido quando o usuário troca de tema."""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_THEME = "aurora"

THEMES: dict[str, dict[str, Any]] = {
    "aurora": {
        "name": "Aurora", "background": "#14112B", "foreground": "#F4F2FF", "muted": "#B9B3E6",
        "accent": "#8B7CFF", "accentText": "#FFFFFF", "surface": "#221D45",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "minimal": {
        "name": "Minimal", "background": "#FAFAF7", "foreground": "#17181C", "muted": "#5B5F6B",
        "accent": "#2F6BFF", "accentText": "#FFFFFF", "surface": "#EEF0F4",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "grafite": {
        "name": "Grafite", "background": "#1B1D22", "foreground": "#F2F2F2", "muted": "#A7ABB5",
        "accent": "#F5A524", "accentText": "#1B1D22", "surface": "#2A2D35",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "oceano": {
        "name": "Oceano", "background": "#0B2239", "foreground": "#EAF6FF", "muted": "#9CC3DF",
        "accent": "#2EC4E6", "accentText": "#0B2239", "surface": "#12324F",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "terracota": {
        "name": "Terracota", "background": "#FBF4EC", "foreground": "#2E1F17", "muted": "#7A5E4E",
        "accent": "#C8553D", "accentText": "#FFFFFF", "surface": "#F1E3D3",
        "font": "Georgia", "headingFont": "Georgia",
    },
    "floresta": {
        "name": "Floresta", "background": "#0F241C", "foreground": "#EEF7EF", "muted": "#A9C8B1",
        "accent": "#8BD450", "accentText": "#0F241C", "surface": "#18382B",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "rosa": {
        "name": "Rosa", "background": "#FFF5F8", "foreground": "#2B1020", "muted": "#7E5169",
        "accent": "#D63384", "accentText": "#FFFFFF", "surface": "#FBE3EC",
        "font": "Segoe UI", "headingFont": "Segoe UI Semibold",
    },
    "corporativo": {
        "name": "Corporativo", "background": "#FFFFFF", "foreground": "#1A2233", "muted": "#566176",
        "accent": "#0B5FFF", "accentText": "#FFFFFF", "surface": "#EDF2FB",
        "font": "Calibri", "headingFont": "Calibri",
    },
}


def get_theme(theme_id: str | None) -> dict[str, Any]:
    key = theme_id if theme_id in THEMES else DEFAULT_THEME
    theme = copy.deepcopy(THEMES[key])
    theme["id"] = key
    return theme


def list_themes() -> list[dict[str, Any]]:
    return [get_theme(k) for k in THEMES]


def role_color(theme: dict[str, Any], role: str | None, fallback: str) -> str:
    """Cor de um papel (role) dentro do tema."""
    mapping = {
        "title": theme.get("foreground"),
        "body": theme.get("foreground"),
        "muted": theme.get("muted"),
        "accent": theme.get("accent"),
        "on-accent": theme.get("accentText"),
        "accent-fill": theme.get("accent"),
        "surface-fill": theme.get("surface"),
        "on-image": "#FFFFFF",
        "overlay": "#000000",
    }
    return mapping.get(role or "", None) or fallback
