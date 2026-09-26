"""Estilo visual da interface do IAVOX, inspirado no mockup enviado por Aldeir:
painel lateral claro, cartões brancos com cantos arredondados, acentos em azul,
botões grandes e arredondados (play/ação principal) — visual limpo e acessível."""

ACCENT = "#1f6fd6"
ACCENT_DARK = "#155aad"
ACCENT_LIGHT = "#eaf2fd"
SIDEBAR_BG = "#ffffff"
CARD_BG = "#ffffff"
PAGE_BG = "#f3f5f8"
TEXT_DARK = "#1c2733"
TEXT_MUTED = "#6b7686"
BORDER = "#e1e6ec"

STYLESHEET = f"""
QMainWindow {{
    background-color: {PAGE_BG};
}}

QWidget#sidebar {{
    background-color: {SIDEBAR_BG};
    border-right: 1px solid {BORDER};
}}

QLabel#brandTitle {{
    color: white;
    font-size: 16px;
    font-weight: 600;
    padding: 14px 16px;
}}

QWidget#brandBar {{
    background-color: {ACCENT};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QListWidget#historyList {{
    background-color: transparent;
    border: none;
    font-size: 13px;
    color: {TEXT_DARK};
    outline: 0;
}}

QListWidget#historyList::item {{
    padding: 10px 14px;
    border-bottom: 1px solid {BORDER};
}}

QListWidget#historyList::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_DARK};
    border-radius: 6px;
}}

QLabel#sectionLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 10px 14px 2px 14px;
    text-transform: uppercase;
}}

QFrame.card {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

QLabel#docTitle {{
    color: {TEXT_DARK};
    font-size: 15px;
    font-weight: 600;
}}

QLabel#docSubtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QLabel#pageHeading {{
    color: {TEXT_DARK};
    font-size: 20px;
    font-weight: 700;
}}

QComboBox, QLineEdit {{
    background-color: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    color: {TEXT_DARK};
    font-size: 13px;
}}

QComboBox::drop-down {{
    border: none;
}}

QCheckBox {{
    color: {TEXT_DARK};
    font-size: 13px;
    spacing: 8px;
}}

QPushButton {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_DARK};
    border: none;
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: #dcebfb;
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: white;
    border-radius: 24px;
    padding: 14px 28px;
    font-size: 14px;
    font-weight: 700;
}}

QPushButton#primaryButton:hover {{
    background-color: {ACCENT_DARK};
}}

QPushButton#primaryButton:disabled {{
    background-color: #a9c6ea;
}}

QPushButton#playCircle {{
    background-color: {ACCENT};
    color: white;
    border-radius: 32px;
    font-size: 20px;
    font-weight: 700;
}}

QPushButton#playCircle:hover {{
    background-color: {ACCENT_DARK};
}}

QPushButton#secondaryPill {{
    background-color: white;
    color: {ACCENT};
    border: 1.5px solid {ACCENT};
    border-radius: 20px;
    padding: 10px 20px;
    font-weight: 600;
}}

QPushButton#secondaryPill:hover {{
    background-color: {ACCENT_LIGHT};
}}

QProgressBar {{
    border: none;
    border-radius: 6px;
    background-color: {BORDER};
    height: 10px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 6px;
}}

QTextEdit#logBox {{
    background-color: #fbfcfd;
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_MUTED};
    font-family: monospace;
    font-size: 12px;
}}

QLabel#statusChip {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_DARK};
    border-radius: 10px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}}
"""
