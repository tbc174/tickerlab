"""Guia: como usar o app e o glossário.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src.conteudo import carregar_sobre, proteger_cifrao
from telas.comum import cabecalho_da_pagina, obter_glossario
from telas.estrategias.comum import obter_estrategias


def secao_sobre():
    st.subheader("Sobre o TickerLab")
    aba_metodo, aba_glossario, aba_estrategias = st.tabs(
        ["Metodologia e limites", "Glossário", "Estratégias"]
    )
    with aba_metodo:
        for titulo, texto in carregar_sobre().items():
            st.markdown(f"#### {titulo}")
            st.markdown(proteger_cifrao(texto))
    with aba_glossario:
        _lista_de_verbetes(
            obter_glossario(), "Buscar no glossário", "sobre_busca_glossario"
        )
    with aba_estrategias:
        _lista_de_verbetes(
            obter_estrategias(), "Buscar nas estratégias", "sobre_busca_estrategias"
        )


def _lista_de_verbetes(verbetes, rotulo_da_busca, chave):
    busca = st.text_input(rotulo_da_busca, key=chave).strip().lower()
    achados = {
        termo: texto
        for termo, texto in verbetes.items()
        if busca in termo.lower() or busca in texto.lower()
    }
    st.caption(f"{len(achados)} de {len(verbetes)} verbetes.")
    for termo, texto in achados.items():
        with st.expander(termo):
            st.markdown(proteger_cifrao(texto))


def pagina_guia():
    cabecalho_da_pagina("guia")
    secao_sobre()
