"""Termos de uso e política de privacidade (textos em conteudo/).

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src.conformidade import VERSAO_DOS_TERMOS, carregar_texto
from telas.comum import cabecalho_da_pagina


def _corpo_do_texto(nome):
    """O texto legal sem o título da primeira linha (o título vem do cabeçalho da página)."""
    texto = carregar_texto(nome)
    return texto.split("\n", 1)[1].lstrip() if texto.startswith("# ") else texto


def pagina_termos():
    cabecalho_da_pagina("termos")
    st.markdown(_corpo_do_texto("termos"))
    st.caption(f"Versão dos termos: {VERSAO_DOS_TERMOS}.")


def pagina_privacidade():
    cabecalho_da_pagina("privacidade")
    st.markdown(_corpo_do_texto("privacidade"))
    st.caption(f"Versão da política: {VERSAO_DOS_TERMOS}.")
