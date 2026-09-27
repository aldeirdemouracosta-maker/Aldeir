"""
Tema oficial do IAVOX (especificação "IAVOX — Especificação oficial do tema"):
fundo azul profundo, cartões com borda azul elétrico, foco amarelo bem
visível, badges de status verde/amarelo/vermelho, fonte Inter (com
alternativas do sistema), botões grandes e alto contraste.
"""

AZUL_PROFUNDO = "#0B1426"
AZUL_PAINEL = "#0F1D36"
AZUL_CARTAO = "#11213F"
AZUL_ELETRICO = "#00A7FF"
CIANO = "#00E5FF"
BRANCO = "#F2F6FF"
TEXTO_SUAVE = "#A9B8D6"
AMARELO_FOCO = "#FFC62B"
VERDE_OK = "#00E676"
VERMELHO_ALERTA = "#FF4D4D"
BORDA = "#1E4F8F"

FONTE = '"Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'

STYLESHEET = f"""
* {{
    font-family: {FONTE};
    color: {BRANCO};
}}
QMainWindow, QWidget#raiz, QStackedWidget, QWidget#pagina {{
    background-color: {AZUL_PROFUNDO};
}}
QToolTip {{
    background-color: {AZUL_PAINEL};
    color: {BRANCO};
    border: 1px solid {AZUL_ELETRICO};
    padding: 6px;
}}

/* ---------- títulos ---------- */
QLabel#logo {{ font-size: 64px; font-weight: 800; letter-spacing: 2px; }}
QLabel#slogan {{ color: {AZUL_ELETRICO}; font-size: 24px; font-weight: 600; }}
QLabel#subslogan {{ color: {TEXTO_SUAVE}; font-size: 15px; }}
QLabel#tituloPagina {{ font-size: 28px; font-weight: 700; }}
QLabel#descricaoPagina {{ color: {TEXTO_SUAVE}; font-size: 15px; }}
QLabel#rotuloSecao {{
    color: {CIANO}; font-size: 12px; font-weight: 600; letter-spacing: 1px;
}}
QLabel#textoSuave {{ color: {TEXTO_SUAVE}; font-size: 14px; }}

/* ---------- balão de fala do robô ---------- */
QFrame#balao {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {AZUL_ELETRICO};
    border-radius: 18px;
}}
QLabel#balaoTexto {{ font-size: 16px; }}

/* ---------- badges ---------- */
QLabel#badge {{
    border: 2px solid {AZUL_ELETRICO};
    border-radius: 14px;
    padding: 4px 18px;
    color: {AZUL_ELETRICO};
    font-size: 15px;
    font-weight: 700;
    background-color: rgba(0, 167, 255, 0.08);
}}

/* ---------- cartões F1..F5 ---------- */
QFrame#cartao {{
    background-color: {AZUL_CARTAO};
    border: 1px solid {BORDA};
    border-radius: 18px;
}}
QFrame#cartao:hover {{ border: 1px solid {AZUL_ELETRICO}; }}
QFrame#cartao:focus {{ border: 3px solid {AMARELO_FOCO}; }}
QFrame#cartaoDestaque {{
    background-color: {AZUL_CARTAO};
    border: 2px solid {AMARELO_FOCO};
    border-radius: 18px;
}}
QFrame#cartaoDestaque:focus {{ border: 4px solid {AMARELO_FOCO}; background-color: #1A2A40; }}
QLabel#tecla {{ color: {AZUL_ELETRICO}; font-size: 26px; font-weight: 700; }}
QLabel#teclaDestaque {{ color: {AMARELO_FOCO}; font-size: 30px; font-weight: 700; }}
QLabel#nomeCartao {{ font-size: 26px; font-weight: 700; }}
QLabel#descCartao {{ color: {BRANCO}; font-size: 17px; }}

/* ---------- painéis ---------- */
QFrame#painel {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 16px;
}}
QLabel#teclaAtalho {{
    border: 1px solid {AZUL_ELETRICO};
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 13px;
    font-weight: 600;
    background-color: {AZUL_PROFUNDO};
}}

/* ---------- barra de navegação ---------- */
QFrame#barraNav {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 22px;
}}
QPushButton#botaoNav {{
    background: transparent;
    border: 2px solid transparent;
    border-radius: 16px;
    padding: 12px 22px;
    font-size: 19px;
    text-align: center;
}}
QPushButton#botaoNav:hover {{ background-color: rgba(0, 167, 255, 0.10); }}
QPushButton#botaoNav:checked {{
    border: 2px solid {AZUL_ELETRICO};
    color: {AZUL_ELETRICO};
    background-color: rgba(0, 167, 255, 0.10);
}}
QPushButton#botaoNav:focus {{ border: 3px solid {AMARELO_FOCO}; }}

/* ---------- barra de status ---------- */
QFrame#barraStatus {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 22px;
}}
QPushButton#itemStatus {{
    background: transparent;
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 6px 12px;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton#itemStatus:focus {{ border: 2px solid {AMARELO_FOCO}; }}

/* ---------- botões comuns ---------- */
QPushButton {{
    background-color: {AZUL_CARTAO};
    border: 2px solid {AZUL_ELETRICO};
    border-radius: 14px;
    padding: 10px 20px;
    font-size: 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #16305A; }}
QPushButton:focus {{ border: 3px solid {AMARELO_FOCO}; }}
QPushButton:disabled {{ color: #5D6B86; border-color: #2A3B5C; }}
QPushButton#botaoPrimario {{
    background-color: {AZUL_ELETRICO};
    color: {AZUL_PROFUNDO};
    border: 2px solid {AZUL_ELETRICO};
    font-size: 18px;
    padding: 12px 28px;
}}
QPushButton#botaoPrimario:hover {{ background-color: {CIANO}; }}
QPushButton#botaoPrimario:focus {{ border: 3px solid {AMARELO_FOCO}; }}
QPushButton#botaoPrimario:disabled {{ background-color: #1E4F8F; color: #5D6B86; }}
QPushButton#botaoPlay {{
    background-color: {AZUL_ELETRICO};
    border: 3px solid {CIANO};
    border-radius: 36px;
    color: {BRANCO};
    font-size: 26px;
    padding: 0;
}}
QPushButton#botaoPlay:focus {{ border: 4px solid {AMARELO_FOCO}; }}
QPushButton#botaoPlay:disabled {{ background-color: #1E4F8F; border-color: #2A3B5C; }}
QPushButton#botaoVoltar {{ border: 2px solid {BORDA}; font-size: 15px; padding: 8px 16px; }}
QPushButton#botaoPerigo {{ border-color: {VERMELHO_ALERTA}; }}

/* ---------- campos ---------- */
QTextEdit, QPlainTextEdit, QLineEdit, QListWidget {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 12px;
    padding: 10px;
    font-size: 17px;
    selection-background-color: {AZUL_ELETRICO};
    selection-color: {AZUL_PROFUNDO};
}}
QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus {{
    border: 2px solid {AMARELO_FOCO};
}}
QListWidget::item {{ padding: 10px; border-bottom: 1px solid {BORDA}; }}
QListWidget::item:selected {{ background-color: #16305A; color: {BRANCO}; }}
QComboBox {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 15px;
    min-width: 170px;
}}
QComboBox:focus {{ border: 2px solid {AMARELO_FOCO}; }}
QComboBox QAbstractItemView {{
    background-color: {AZUL_PAINEL};
    selection-background-color: {AZUL_ELETRICO};
    selection-color: {AZUL_PROFUNDO};
}}
QCheckBox {{ font-size: 15px; spacing: 10px; }}
QCheckBox:focus {{ color: {AMARELO_FOCO}; }}
QCheckBox::indicator {{ width: 20px; height: 20px; border: 2px solid {AZUL_ELETRICO}; border-radius: 5px; }}
QCheckBox::indicator:checked {{ background-color: {AZUL_ELETRICO}; }}
QProgressBar {{
    background-color: {AZUL_PAINEL};
    border: 1px solid {BORDA};
    border-radius: 8px;
    height: 14px;
    text-align: center;
    font-size: 12px;
}}
QProgressBar::chunk {{ background-color: {AZUL_ELETRICO}; border-radius: 7px; }}
QScrollBar:vertical {{ background: {AZUL_PROFUNDO}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {BORDA}; border-radius: 6px; min-height: 30px; }}
QDialog {{ background-color: {AZUL_PROFUNDO}; }}
QMessageBox {{ background-color: {AZUL_PROFUNDO}; }}
QMessageBox QLabel {{ font-size: 15px; }}
"""
