"""O tema do app que a pessoa escolheu (claro, escuro ou automático) e o script que o aplica.

A escolha fica nas preferências da conta (`"tema"`); o script vai na página a cada execução e usa
os mesmos arquivos do site (`static/tema/sol.js`) mais o `static/tema/app.js`. Detalhes de como o
Streamlit guarda o tema estão no app.js; um teste confere a chave a cada atualização do Streamlit.
"""

import json
from pathlib import Path

ESCOLHAS = ("auto", "claro", "escuro")
NOMES = {"auto": "Automático", "claro": "Claro", "escuro": "Escuro"}
PADRAO = "auto"
# o número no fim da chave em que o Streamlit guarda o tema ("stActiveTheme-<página>-v2")
VERSAO_DA_CHAVE_DO_STREAMLIT = 2

PASTA_DO_TEMA = Path(__file__).resolve().parent.parent / "static" / "tema"


def normalizar(escolha: object) -> str:
    """A escolha guardada, ou o Automático quando ela falta ou não é uma das três."""
    return escolha if isinstance(escolha, str) and escolha in ESCOLHAS else PADRAO


def script(escolha: str, paginas: list[str]) -> str:
    """O <script> que aplica a escolha no navegador (para o `st.html` com JavaScript ligado)."""
    sol = (PASTA_DO_TEMA / "sol.js").read_text(encoding="utf-8")
    app = (PASTA_DO_TEMA / "app.js").read_text(encoding="utf-8")
    chamada = (
        f"window.TickerLabTemaDoApp.aplicar({json.dumps(normalizar(escolha))}, "
        f"{json.dumps(paginas)}, {VERSAO_DA_CHAVE_DO_STREAMLIT});"
    )
    return f"<script>{sol}\n{app}\n{chamada}</script>"
