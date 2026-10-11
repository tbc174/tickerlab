"""Tokens de design do painel (um valor por papel) e a folha de estilo gerada a partir deles.

Valores do documento de design (seção 3). Regras: tema escuro sem preto puro; elevação pela cor
(quanto mais alto, mais clara a superfície); ganho/perda em azul/vermelho SEMPRE com sinal e seta;
cores de estado sempre com ícone e texto; grade de 8 px; Segoe UI Variable.
"""

from __future__ import annotations

CORES = {
    "fundo": "#121212",  # nível 0: janela
    "superficie": "#1a1a19",  # nível 1: cartões e gráficos
    "elevado": "#242422",  # nível 2: menus, detalhes
    "hover": "#2c2c2a",  # nível 3: passar o mouse
    "texto": "#ececea",
    "texto_secundario": "#c3c2b7",
    "texto_apagado": "#898781",
    "grade": "#2c2c2a",
    "eixo": "#383835",
    "borda": "rgba(255, 255, 255, 26)",  # branco a 10%
    "acento": "#3987e5",
    "acento_hover": "#4f97ec",
    "acento_pressionado": "#2a78d6",
    "ganho": "#3987e5",
    "perda": "#e66767",
    "bom": "#0ca30c",
    "atencao": "#fab219",
    "serio": "#ec835a",
    "critico": "#d03b3b",
}
# ordem fixa, validada para daltonismo no modo escuro; a cor segue a série, nunca a posição
SERIES = (
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
)
ESTADOS = {  # cor, ícone e texto andam juntos
    "bom": (CORES["bom"], "✓"),
    "atencao": (CORES["atencao"], "⚠"),
    "serio": (CORES["serio"], "⚠"),
    "critico": (CORES["critico"], "✕"),
}
ESPACO = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24, "xxl": 32, "xxxl": 48}
RAIO = {"cartao": 8, "controle": 4}
FONTE = "Segoe UI Variable"
FONTE_DE_ICONES = "Segoe Fluent Icons"
TAMANHO = {
    "rotulo": 12,
    "corpo": 14,
    "titulo_cartao": 16,
    "titulo_tela": 24,
    "destaque": 32,
}
ALTURA_DO_BOTAO = 32
ALVO_MINIMO = 24


def seta(valor: float) -> str:
    """Seta e sinal que acompanham a cor de ganho/perda (nunca a cor sozinha)."""
    if valor > 0:
        return "▲"
    if valor < 0:
        return "▼"
    return "■"


def cor_da_variacao(valor: float) -> str:
    if valor > 0:
        return CORES["ganho"]
    if valor < 0:
        return CORES["perda"]
    return CORES["texto_secundario"]


def folha_de_estilo() -> str:
    c, e, r = CORES, ESPACO, RAIO
    return f"""
* {{
    font-family: "{FONTE}", "Segoe UI", sans-serif;
    font-size: {TAMANHO["corpo"]}px;
    color: {c["texto"]};
}}
QMainWindow, QWidget#fundo, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {c["fundo"]};
}}
QWidget#navegacao {{
    background: {c["superficie"]};
    border-right: 1px solid {c["borda"]};
}}
QPushButton#item_de_navegacao {{
    text-align: left;
    padding: {e["s"]}px {e["m"]}px;
    min-height: {ALTURA_DO_BOTAO + 4}px;
    border: none;
    border-radius: {r["controle"]}px;
    background: transparent;
    color: {c["texto_secundario"]};
}}
QPushButton#item_de_navegacao:hover {{ background: {c["hover"]}; color: {c["texto"]}; }}
QPushButton#item_de_navegacao:checked {{
    background: {c["elevado"]};
    color: {c["texto"]};
    border-left: 3px solid {c["acento"]};
    font-weight: 600;
}}
QFrame#cartao {{
    background: {c["superficie"]};
    border: 1px solid {c["borda"]};
    border-radius: {r["cartao"]}px;
}}
QLabel {{ background: transparent; }}
QLabel[papel="titulo_tela"] {{ font-size: {TAMANHO["titulo_tela"]}px; font-weight: 600; }}
QLabel[papel="subtitulo_tela"] {{ color: {c["texto_secundario"]}; }}
QLabel[papel="titulo_cartao"] {{ font-size: {TAMANHO["titulo_cartao"]}px; font-weight: 600; }}
QLabel[papel="destaque"] {{ font-size: {TAMANHO["destaque"]}px; font-weight: 600; }}
QLabel[papel="secundario"] {{ color: {c["texto_secundario"]}; }}
QLabel[papel="apagado"] {{ color: {c["texto_apagado"]}; font-size: {TAMANHO["rotulo"]}px; }}
QLabel[papel="info"] {{ color: {c["texto_apagado"]}; font-size: {TAMANHO["rotulo"]}px; }}
QPushButton {{
    min-height: {ALTURA_DO_BOTAO}px;
    padding: 0 {e["l"]}px;
    border-radius: {r["controle"]}px;
    border: 1px solid {c["borda"]};
    background: {c["elevado"]};
}}
QPushButton:hover {{ background: {c["hover"]}; }}
QPushButton:disabled {{ color: {c["texto_apagado"]}; background: {c["superficie"]}; }}
QPushButton[papel="primario"] {{
    background: {c["acento"]};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[papel="primario"]:hover {{ background: {c["acento_hover"]}; }}
QPushButton[papel="primario"]:pressed {{ background: {c["acento_pressionado"]}; }}
QPushButton[papel="primario"]:disabled {{ background: {c["hover"]}; color: {c["texto_apagado"]}; }}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTableView:focus {{
    outline: none;
    border: 1px solid {c["acento"]};
}}
QLineEdit, QComboBox {{
    min-height: {ALTURA_DO_BOTAO}px;
    padding: 0 {e["s"]}px;
    border: 1px solid {c["borda"]};
    border-radius: {r["controle"]}px;
    background: {c["elevado"]};
}}
QComboBox QAbstractItemView {{
    background: {c["elevado"]};
    selection-background-color: {c["hover"]};
    border: 1px solid {c["borda"]};
}}
QTableView {{
    background: {c["superficie"]};
    border: none;
    gridline-color: transparent;
    selection-background-color: {c["hover"]};
    selection-color: {c["texto"]};
}}
QTableView::item {{ padding: 0 {e["s"]}px; border-bottom: 1px solid {c["grade"]}; }}
QHeaderView::section {{
    background: {c["superficie"]};
    color: {c["texto_apagado"]};
    font-size: {TAMANHO["rotulo"]}px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid {c["eixo"]};
    padding: {e["s"]}px;
}}
QTableCornerButton::section {{ background: {c["superficie"]}; border: none; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: {c["hover"]}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {c["eixo"]}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; width: 0; height: 0;
}}
QToolTip {{
    background: {c["elevado"]};
    color: {c["texto"]};
    border: 1px solid {c["borda"]};
    padding: {e["s"]}px;
}}
QProgressBar {{
    background: {c["hover"]};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {c["acento"]}; border-radius: 3px; }}
QStatusBar {{
    background: {c["superficie"]};
    border-top: 1px solid {c["borda"]};
    color: {c["texto_secundario"]};
}}
QStatusBar QLabel {{ color: {c["texto_secundario"]}; font-size: {TAMANHO["rotulo"]}px; padding: 0 {e["m"]}px; }}
QFrame#aviso {{
    background: {c["elevado"]};
    border: 1px solid {c["borda"]};
    border-radius: {r["cartao"]}px;
}}
"""
