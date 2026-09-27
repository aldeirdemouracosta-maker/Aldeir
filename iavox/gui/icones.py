"""Ícones de linha do IAVOX, desenhados em SVG (sem arquivos externos)."""
from __future__ import annotations

from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

_TRACO = 'fill="none" stroke="{cor}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'

_SVGS = {
    "documento": """<path d="M6 2.5h8l4.5 4.5v14.5H6z" fill="{cor}" opacity=".9"/>
        <path d="M14 2.5v4.5h4.5" fill="#0B1426" opacity=".35"/>
        <g stroke="#F2F6FF" stroke-width="1.4" stroke-linecap="round">
        <line x1="8.8" y1="11" x2="15.7" y2="11"/><line x1="8.8" y1="14" x2="15.7" y2="14"/>
        <line x1="8.8" y1="17" x2="13.5" y2="17"/></g>""",
    "fala": """<g {t}><path d="M3.5 11a7 6 0 1 1 3.3 5.1L3.5 18l1-3.4A6 6 0 0 1 3.5 11z"/>
        <line x1="7.5" y1="9.8" x2="13.5" y2="9.8"/><line x1="7.5" y1="12.6" x2="11.8" y2="12.6"/>
        <path d="M19 7.5a6 6 0 0 1 0 7"/><path d="M21.5 5.5a9 9 0 0 1 0 11"/></g>""",
    "olho": """<g {t}><path d="M3 7V4h3M18 4h3v3M21 17v3h-3M6 20H3v-3"/>
        <path d="M4.5 12s2.8-4.5 7.5-4.5 7.5 4.5 7.5 4.5-2.8 4.5-7.5 4.5S4.5 12 4.5 12z"/></g>
        <circle cx="12" cy="12" r="2.2" fill="{cor}"/>""",
    "livro": """<g {t}><path d="M12 6.5c-2-1.6-5-2-8.5-1.5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5c-3.5-.5-6.5-.1-8.5 1.5z"/>
        <line x1="12" y1="6.5" x2="12" y2="19.5"/></g>""",
    "estrela": """<path d="M12 3.2l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.6l-5.3 2.9 1.1-5.9-4.4-4.1 6-.8z" fill="{cor}"/>""",
    "casa": """<g {t}><path d="M3.5 11 12 4l8.5 7"/><path d="M6 9.5V20h4.5v-5h3v5H18V9.5"/></g>""",
    "atividade": """<g {t}><rect x="3" y="4" width="18" height="16" rx="3"/>
        <path d="M6 12.5h2.5l1.5-3.5 2.5 7 1.8-4.5H18"/></g>""",
    "ajuda": """<g {t}><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.6 2.6 0 1 1 3.6 2.4c-.7.3-1.1.9-1.1 1.6v.6"/></g>
        <circle cx="12" cy="17" r="1" fill="{cor}"/>""",
    "engrenagem": """<g {t}><circle cx="12" cy="12" r="3"/>
        <path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>
        <circle cx="12" cy="12" r="6.3"/></g>""",
    "microfone": """<g {t}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0"/>
        <line x1="12" y1="17.5" x2="12" y2="21"/></g>""",
    "ocr": """<g {t}><path d="M3 7V4h3M18 4h3v3M21 17v3h-3M6 20H3v-3"/><path d="M8.5 16.5 12 7.5l3.5 9M9.8 13.3h4.4"/></g>""",
    "cubo": """<g {t}><path d="M12 3 20 7.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/></g>""",
    "onda": """<g {t}><circle cx="12" cy="12" r="9"/>
        <path d="M8 10v4M10 8.5v7M12 7v10M14 8.5v7M16 10v4"/></g>""",
    "voltar": """<g {t}><path d="M10 6 4 12l6 6M4 12h16"/></g>""",
    "seta": """<g {t}><circle cx="12" cy="12" r="9.5"/><path d="M10.5 8l4 4-4 4"/></g>""",
}


def svg(nome: str, cor: str = "#00A7FF") -> bytes:
    corpo = _SVGS[nome].replace("{t}", _TRACO).replace("{cor}", cor)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{corpo}</svg>'.encode()


def pixmap(nome: str, tamanho: int, cor: str = "#00A7FF") -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(nome, cor)))
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return pm


def icone(nome: str, tamanho: int = 32, cor: str = "#00A7FF") -> QIcon:
    return QIcon(pixmap(nome, tamanho, cor))
