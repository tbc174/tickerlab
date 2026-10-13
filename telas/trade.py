"""TickerLab Trade: a página sobre a pesquisa de trading.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src import trade
from telas.comum import cabecalho_da_pagina


def pagina_trade():
    fase = trade.fase_atual()
    st.markdown(
        f'<span class="tl-estado">Em pesquisa · fase {fase.codigo}</span>',
        unsafe_allow_html=True,
    )
    cabecalho_da_pagina("trade")
    st.markdown(
        "Uma pesquisa de **trading quantitativo**: modelos de aprendizado de máquina testados "
        "em mais de 80 ativos (ações, índices, moedas, juros, commodities e cripto), com regras "
        "de aprovação **escritas antes de olhar os resultados**. Só se um modelo passar, ele "
        "vira um robô numa **conta de demonstração** do MetaTrader 5, sem dinheiro de verdade. "
        "Resultado negativo também é publicado."
    )
    fases = "".join(
        f'<div class="tl-fase {f.estado}"><b>{f.codigo}'
        f"{' ✓' if f.estado == trade.FEITA else ' ●' if f.estado == trade.AGORA else ''}"
        f"</b>{f.nome}</div>"
        for f in trade.FASES
    )
    st.markdown(f'<div class="tl-fases">{fases}</div>', unsafe_allow_html=True)
    st.caption(f"Agora: {fase.nome}. {fase.explicacao}")

    st.subheader("Downloads")
    for coluna, item in zip(
        st.columns(len(trade.DOWNLOADS)), trade.DOWNLOADS, strict=True
    ):
        with coluna, st.container(border=True):
            st.markdown(f"**{item.titulo}**")
            st.caption(item.descricao)
            st.button(
                "Disponível no fim do projeto",
                key=f"download_{item.titulo}",
                disabled=not item.disponivel,
                width="stretch",
            )
    st.warning(
        "É uma pesquisa educacional. Nada aqui é recomendação de investimento, e nenhum teste "
        "garante rentabilidade.",
        icon=":material/info:",
    )
