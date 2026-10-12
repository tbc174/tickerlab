"""Estratégias: regimes de mercado, filtro por regime e disjuntor.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import pandas as pd
import streamlit as st

from src import graficos
from src import indicadores as ind
from src.backtest import executar_backtest
from src.estrategias import gerar_posicao
from src.regimes import (
    REGIMES_DE_TENDENCIA,
    REGIMES_DE_VOLATILIDADE,
    aplicar_disjuntor_de_drawdown,
    classificar_regimes_de_tendencia,
    classificar_regimes_de_volatilidade,
    filtrar_por_regime,
    gerir_pela_variancia,
    resumir_por_regime,
    varrer_disjuntor,
)
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_metrica,
    formatar_pct,
    mostrar_grafico,
)
from telas.estrategias.comum import (
    ESTRATEGIA_DE_REFERENCIA,
    _custo_do_experimento,
    _escolher_estrategia_simples,
    _tabela_de_resultados,
)

CORES_DOS_REGIMES = {
    "Calmo": graficos.COR_ALTA,
    "Agitado": graficos.COR_QUEDA,
    "Alta": graficos.COR_ALTA,
    "Baixa": graficos.COR_QUEDA,
}


def _escolher_regimes(chave, fechamento):
    """Controles do tipo de regime; devolve (regimes, nomes possíveis, descrição)."""
    criterio = st.radio(
        "Como separar os regimes",
        ["Volatilidade (calmo × agitado)", "Tendência (alta × baixa)"],
        horizontal=True,
        key=f"{chave}_criterio",
        help=ajuda_do("Regime de mercado"),
    )
    if criterio.startswith("Volatilidade"):
        c1, c2 = st.columns(2)
        janela = c1.slider(
            "Janela da volatilidade (dias)", 5, 60, 20, 1, key=f"{chave}_jan_vol"
        )
        percentil = c2.slider(
            "Agitado acima do percentil",
            0.3,
            0.9,
            0.5,
            0.05,
            key=f"{chave}_percentil",
            help="0,5 = a mediana: metade dos dias, em média, é chamada de agitada.",
        )
        regimes = classificar_regimes_de_volatilidade(fechamento, janela, percentil)
        return regimes, REGIMES_DE_VOLATILIDADE, f"volatilidade de {janela} dias"
    janela = st.slider("Média móvel (dias)", 20, 300, 200, 10, key=f"{chave}_jan_tend")
    regimes = classificar_regimes_de_tendencia(fechamento, janela)
    return regimes, REGIMES_DE_TENDENCIA, f"preço contra a média de {janela} dias"


def _tabela_de_regimes(resumo):
    exibicao = pd.DataFrame(index=resumo.index)
    exibicao["Dias"] = resumo["Dias"].astype(int)
    exibicao["% do tempo"] = [formatar_pct(v) for v in resumo["% do tempo"]]
    exibicao["Retorno médio por dia"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno médio por dia"]
    ]
    exibicao["Retorno anualizado"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno anualizado"]
    ]
    exibicao["Volatilidade anual"] = [
        formatar_pct(v) for v in resumo["Volatilidade anual"]
    ]
    exibicao["Índice de Sharpe"] = [
        formatar_metrica("Sharpe", v) for v in resumo["Índice de Sharpe"]
    ]
    exibicao["Pior dia"] = [formatar_pct(v) for v in resumo["Pior dia"]]
    return exibicao


def _regimes_do_ativo(dados, taxa_livre_de_risco):
    st.markdown("**Como o ativo se comporta em cada regime**")
    fechamento = dados["Close"]
    regimes, nomes, descricao = _escolher_regimes("reg_ativo", fechamento)
    try:
        resumo = resumir_por_regime(
            ind.calcular_retorno_diario(fechamento).fillna(0.0),
            regimes,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_regimes(
            fechamento, regimes, {n: CORES_DOS_REGIMES[n] for n in nomes}
        )
    )
    st.dataframe(_tabela_de_regimes(resumo), width="stretch")
    st.caption(
        f"Regime pelo critério: {descricao}. Cada dia é contado no regime da véspera, "
        "que é o que dava para saber antes do pregão. Se a volatilidade for bem maior no "
        "regime agitado e o retorno não compensar, fugir dele pode valer a pena; a próxima "
        "aba testa isso com uma estratégia."
    )


def _filtro_por_regime(dados, taxa_livre_de_risco):
    st.markdown("**Operar só em certos regimes**")
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_filtro")
    custo = _custo_do_experimento("reg_filtro")
    regimes, nomes, descricao = _escolher_regimes("reg_filtro", fechamento)
    ficar_em = st.multiselect(
        "Ficar comprado nos regimes",
        list(nomes),
        default=[nomes[0]],
        key=f"reg_filtro_ficar_em_{nomes[0]}",
    )
    usar_variancia = st.checkbox(
        "Comparar também a variância gerida (posição menor quando a variância sobe)",
        key="reg_filtro_variancia",
        help=ajuda_do("Variância gerida"),
    )
    try:
        posicao = gerar_posicao(nome, dados)
        filtrada = filtrar_por_regime(posicao, regimes, tuple(ficar_em))
        rotulo_filtrado = f"{nome} só em {' e '.join(ficar_em).lower()}"
        resultados = {
            nome: executar_backtest(fechamento, posicao, custo),
            rotulo_filtrado: executar_backtest(fechamento, filtrada, custo),
        }
        if usar_variancia:
            resultados[f"{nome} com variância gerida"] = executar_backtest(
                fechamento, gerir_pela_variancia(fechamento, posicao), custo
            )
        if nome != ESTRATEGIA_DE_REFERENCIA:
            resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
                fechamento, pd.Series(1.0, index=fechamento.index), custo
            )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            destaque=rotulo_filtrado,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        f"Regimes pelo critério: {descricao}. A decisão do fim do dia vale a partir do dia "
        "seguinte e os limites dos regimes usam só o passado. Filtrar costuma reduzir o risco "
        "e a exposição; se o Sharpe também melhora ou se só se perdeu retorno depende do "
        "ativo e do período, e uma única janela de dados não prova nada."
    )


def _disjuntor(dados, taxa_livre_de_risco):
    st.markdown("**Disjuntor de drawdown: se a estratégia cair demais, para**")
    st.caption(ajuda_do("Disjuntor de drawdown"))
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_disj")
    c1, c2, c3 = st.columns(3)
    limite = c1.slider("Dispara com queda de (%)", 3, 40, 15, 1, key="reg_disj_limite")
    pausa = c2.slider("Pausa (dias)", 1, 126, 21, 1, key="reg_disj_pausa")
    with c3:
        custo = _custo_do_experimento("reg_disj")
    try:
        posicao = gerar_posicao(nome, dados)
        disjuntor = aplicar_disjuntor_de_drawdown(
            fechamento, posicao, limite / 100, pausa, custo
        )
        com = executar_backtest(fechamento, disjuntor.posicao, custo)
        sem = executar_backtest(fechamento, posicao, custo)
        varredura = varrer_disjuntor(
            fechamento,
            posicao,
            [0.05, 0.10, 0.20, 0.30],
            [10, 21, 63],
            custo,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    rotulo_com = f"{nome} com disjuntor"
    resultados = {rotulo_com: com, f"{nome} sem disjuntor": sem}
    extras = {
        rotulo_com: {"Disparos": str(len(disjuntor.acionamentos))},
        f"{nome} sem disjuntor": {"Disparos": "0"},
    }
    mostrar_grafico(
        graficos.criar_grafico_disjuntor(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            rotulo_com,
            disjuntor.acionamentos,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco, extras),
        width="stretch",
    )
    st.caption(
        f"O disjuntor ficou {disjuntor.dias_parado} dias travado em caixa. Depois da pausa "
        "o topo é refeito, senão ele dispararia de novo pela mesma queda."
    )
    with st.expander(
        "E se o limite e a pausa fossem outros? (cuidado: é pescar resultado)"
    ):
        exibicao = pd.DataFrame(index=varredura.index)
        exibicao["Retorno total"] = [
            formatar_pct(v, com_sinal=True) for v in varredura["Retorno total"]
        ]
        exibicao["Índice de Sharpe"] = [
            formatar_metrica("Sharpe", v) for v in varredura["Índice de Sharpe"]
        ]
        exibicao["Maior queda"] = [formatar_pct(v) for v in varredura["Maior queda"]]
        exibicao["Disparos"] = varredura["Acionamentos"].astype(int)
        st.dataframe(exibicao, width="stretch")
        st.caption(
            "São 13 linhas testadas no mesmo passado: escolher a melhor é o data snooping "
            "de que falamos na aba Backtest. Olhe o padrão (quanto a queda máxima diminui "
            "e quanto o retorno perde), não o campeão."
        )


def secao_regimes(dados, taxa_livre_de_risco):
    st.subheader("Regimes e disjuntor: o mercado muda de humor")
    st.caption(
        "O mesmo ativo tem fases calmas e fases agitadas. Aqui você vê como ele se "
        "comporta em cada uma, testa uma estratégia que só opera em certas fases e um "
        "disjuntor que a desliga depois de uma queda grande."
    )
    aba_ativo, aba_filtro, aba_disjuntor = st.tabs(
        ["Regimes do ativo", "Estratégia por regime", "Disjuntor de drawdown"]
    )
    with aba_ativo:
        _regimes_do_ativo(dados, taxa_livre_de_risco)
    with aba_filtro:
        _filtro_por_regime(dados, taxa_livre_de_risco)
    with aba_disjuntor:
        _disjuntor(dados, taxa_livre_de_risco)


def pagina_regimes():
    cabecalho_da_pagina("regimes")
    c = carregar_contexto()
    secao_regimes(c.dados, c.taxa_livre_de_risco)
