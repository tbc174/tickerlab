"""A página de relatórios: o estúdio e a biblioteca em abas, com a faixa do tutorial.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src.planos import limites_do
from telas.comum import cabecalho_da_pagina, carregar_contexto, plano_atual
from telas.relatorios.biblioteca import mostrar_biblioteca
from telas.relatorios.estudio import mostrar_estudio
from telas.tutorial import mostrar_tutorial


def pagina_relatorio():
    cabecalho_da_pagina("relatorio")
    c = carregar_contexto()
    # o lugar da faixa fica no topo, mas ela é desenhada no fim: assim já enxerga o que o
    # estúdio acabou de fazer (prévia pronta, carteira carregada) e libera o "Continuar"
    lugar_do_tutorial = st.container()
    usuario = st.session_state.get("usuario")
    limites = limites_do(plano_atual())
    aba_estudio, aba_biblioteca = st.tabs(
        [":material/edit_document: Estúdio", ":material/folder_open: Meus relatórios"]
    )
    with aba_estudio:
        mostrar_estudio(usuario, limites, c)
    with aba_biblioteca:
        mostrar_biblioteca(usuario)
    with lugar_do_tutorial:
        mostrar_tutorial("relatorio", c)
