"""Avançado (Pro): aprendizado de máquina, só com o passado de cada data.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import numpy as np
import pandas as pd
import streamlit as st

from src import aprendizado, graficos
from src.acaso import testar_contra_o_acaso
from src.backtest import executar_backtest
from src.estrategias import gerar_posicao
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_metrica,
    formatar_pct,
    mostrar_grafico,
)
from telas.conta.assinatura import exigir_pagina
from telas.estrategias.comum import (
    ESTRATEGIA_DE_REFERENCIA,
    _custo_do_experimento,
    _escolher_estrategia_simples,
    _tabela_de_resultados,
)


@st.cache_data(show_spinner="Treinando o modelo (só com o passado de cada data)...")
def calcular_previsoes_do_sinal(dados, tipo, alvo, stop, prazo, mascara_bytes=None):
    """Treino com janela que expande; guardado em cache porque leva alguns segundos."""
    if tipo == "dia":
        conjunto = aprendizado.rotular_proximo_dia(dados)
    else:
        conjunto = aprendizado.rotular_barreira_tripla(dados, alvo, stop, prazo)
    mascara = None
    if mascara_bytes is not None:
        sinal = np.frombuffer(mascara_bytes, dtype=bool)
        mascara = sinal[conjunto.posicao]
    return conjunto, aprendizado.prever_fora_da_amostra(conjunto, mascara=mascara)


def _tabela_de_avaliacao(r):
    return pd.DataFrame(
        {
            "Modelo": [
                formatar_pct(r["Acurácia do modelo"]),
                formatar_metrica("Sharpe", r["AUC"]),
                formatar_metrica("Sharpe", r["Brier do modelo"]),
            ],
            "Previsão ingênua": [
                formatar_pct(r["Acurácia ingênua"]),
                "0,50",
                formatar_metrica("Sharpe", r["Brier ingênuo"]),
            ],
        },
        index=[
            "Acurácia (acertos)",
            "AUC (0,5 = acaso)",
            "Erro de Brier (menor é melhor)",
        ],
    )


def _veredito(r):
    z = r["Diferença em erros-padrão"]
    if z >= 2:
        return (
            f"O modelo acertou {formatar_pct(r['Acurácia do modelo'] - r['Acurácia ingênua'], com_sinal=True)} "
            f"a mais que a previsão ingênua, a {formatar_metrica('Sharpe', z)} erros-padrão. "
            "Isso é raro: desconfie antes de comemorar e confira em outro período e outro ativo."
        )
    return (
        f"A diferença para a previsão ingênua foi de {formatar_metrica('Sharpe', z)} "
        "erros-padrão: dentro do que o acaso produz. O modelo não mostrou saber algo "
        "que o preço passado não esconda."
    )


def _ml_sinal_do_dia(dados, taxa_livre_de_risco):
    st.markdown("**Um modelo consegue prever se amanhã sobe?**")
    st.caption(
        "Regressão logística com 8 variáveis simples (retornos, volatilidade, amplitude, "
        "volume, distância da média). Treina só com o passado de cada data, numa janela que "
        "cresce, e é comparada com a previsão ingênua: sempre apostar no lado mais comum."
    )
    c1, c2 = st.columns(2)
    limiar = c1.slider(
        "Compra se a probabilidade passar de", 0.45, 0.65, 0.5, 0.01, key="ml_limiar"
    )
    with c2:
        custo = _custo_do_experimento("ml_dia")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(dados, "dia", 0, 0, 0)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes, limiar)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(f"{int(r['Previsões'])} previsões fora da amostra. " + _veredito(r))

    fechamento = dados["Close"]
    posicao = aprendizado.posicao_a_partir_das_probabilidades(
        previsoes["p"], fechamento.index, limiar
    )
    inicio = previsoes["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        "Modelo (sinal do dia)": executar_backtest(teste, posicao.loc[inicio:], custo),
        ESTRATEGIA_DE_REFERENCIA: executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        ),
    }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Modelo (sinal do dia)",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    try:
        acaso = testar_contra_o_acaso(
            teste, posicao.loc[inicio:], custo, taxa_livre_de_risco
        )
        st.caption(
            f"Teste contra o acaso: p-valor de {formatar_metrica('Sharpe', acaso.p_valor)}. "
            "Abaixo de 0,05, poucas posições sem relação com o preço fariam igual."
        )
    except ValueError as erro:
        st.caption(str(erro))
    st.caption(
        "Só vale o período de teste (depois do primeiro treino). Comprar e segurar é medido "
        "no mesmo período, para a comparação ser justa."
    )


def _ml_barreira_e_meta(dados, taxa_livre_de_risco):
    st.markdown("**Barreira tripla, validação com expurgo e meta-rotulagem**")
    st.caption(ajuda_do("Barreira tripla"))
    c1, c2, c3 = st.columns(3)
    alvo = c1.slider("Alvo (%)", 1, 10, 3, 1, key="ml_alvo")
    stop = c2.slider("Stop (%)", 1, 10, 3, 1, key="ml_stop")
    prazo = c3.slider("Prazo (dias)", 3, 40, 10, 1, key="ml_prazo")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo
        )
        com = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=True)
        sem = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=False)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown(
        "*Quanto o modelo acerta se bate o alvo antes do stop (treino que expande)*"
    )
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(
        f"Em {formatar_pct(r['Fração de 1'])} dos dias o alvo veio antes do stop. "
        + _veredito(r)
    )
    st.markdown("*Validação cruzada em 5 blocos, com e sem expurgo*")
    st.dataframe(
        pd.DataFrame(
            {
                "k-fold comum": [
                    formatar_pct(sem["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", sem["AUC"]),
                ],
                "Com expurgo e embargo": [
                    formatar_pct(com["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", com["AUC"]),
                ],
            },
            index=["Acurácia", "AUC"],
        ),
        width="stretch",
    )
    st.caption(
        "Como cada rótulo olha os próximos dias, exemplos vizinhos do treino e do teste "
        "compartilham o mesmo futuro. O expurgo tira do treino o que encosta no teste e o "
        "embargo deixa uma folga depois dele. Uma diferença grande entre as colunas indica vazamento."
    )

    st.markdown("*Meta-rotulagem: o modelo filtra os sinais de uma regra simples*")
    nome = _escolher_estrategia_simples("ml_meta")
    limiar = st.slider(
        "Age se a probabilidade de sucesso passar de",
        0.4,
        0.7,
        0.5,
        0.01,
        key="ml_meta_limiar",
    )
    custo = _custo_do_experimento("ml_meta")
    fechamento = dados["Close"]
    try:
        base = gerar_posicao(nome, dados)
        sinal = (base > 0).to_numpy()
        conjunto_meta, previsoes_meta = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo, sinal.tobytes()
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    aceitos = previsoes_meta["p"] > limiar
    avaliados = previsoes_meta["p"].notna()
    if avaliados.sum() < 30:
        st.info(
            "Há poucos sinais da regra para treinar o modelo. Use outra regra ou um período maior."
        )
        return
    taxa_geral = conjunto_meta.y[avaliados].mean()
    taxa_aceitos = conjunto_meta.y[aceitos].mean() if aceitos.any() else float("nan")
    meta = base.where(base.index.isin(aceitos[aceitos].index), 0.0)
    inicio = previsoes_meta["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        f"{nome} + meta-modelo": executar_backtest(teste, meta.loc[inicio:], custo),
        nome: executar_backtest(teste, base.loc[inicio:], custo),
    }
    if nome != ESTRATEGIA_DE_REFERENCIA:
        resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        )
    st.caption(
        f"Dos {int(avaliados.sum())} sinais avaliados, o alvo veio primeiro em "
        f"{formatar_pct(taxa_geral)}; nos {int(aceitos.sum())} que o modelo aceitou, em "
        f"{formatar_pct(taxa_aceitos)}."
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque=f"{nome} + meta-modelo",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )


def _ml_volatilidade(dados, taxa_livre_de_risco):
    st.markdown("**Prever a volatilidade (mais fácil que prever o preço)**")
    st.caption(
        "Regressão linear do log da volatilidade futura nas volatilidades de 5, 20 e 60 dias "
        "(estilo HAR), treinada só com o passado. A base de comparação é dizer que os próximos "
        "dias serão iguais aos últimos 20."
    )
    c1, c2, c3 = st.columns(3)
    horizonte = c1.slider("Prever os próximos (dias)", 5, 42, 21, 1, key="ml_horizonte")
    alvo = c2.slider("Alvo de volatilidade (% ao ano)", 5, 40, 15, 1, key="ml_alvo_vol")
    with c3:
        custo = _custo_do_experimento("ml_vol")
    try:
        r = aprendizado.prever_volatilidade(dados, horizonte)
    except ValueError as erro:
        st.info(str(erro))
        return
    m = r.metricas
    cartoes = st.columns(3)
    cartoes[0].metric(
        "Erro do modelo (log)",
        formatar_metrica("Sharpe", m["Erro do modelo (log)"]),
        delta=f"{formatar_metrica('Sharpe', m['Erro ingênuo (log)'])} na previsão ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    cartoes[1].metric(
        "Melhora sobre a ingênua",
        formatar_pct(m["Melhora sobre o ingênuo"], com_sinal=True),
    )
    cartoes[2].metric(
        "Correlação com o que veio",
        formatar_metrica("Sharpe", m["Correlação do modelo"]),
        delta=f"{formatar_metrica('Sharpe', m['Correlação ingênua'])} na ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    mostrar_grafico(
        graficos.criar_grafico_volatilidade_prevista(r.prevista, r.ingenua, r.realizada)
    )
    fechamento = dados["Close"]
    inicio = r.prevista.index[0]
    teste = fechamento.loc[inicio:]
    posicoes = {
        "Alvo com a volatilidade prevista": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.prevista, fechamento.index, alvo / 100
        ),
        "Alvo com a volatilidade dos últimos 20 dias": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.ingenua, fechamento.index, alvo / 100
        ),
    }
    resultados = {
        n: executar_backtest(teste, p.loc[inicio:], custo) for n, p in posicoes.items()
    }
    resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
        teste, pd.Series(1.0, index=teste.index), custo
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Alvo com a volatilidade prevista",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        "A volatilidade é persistente (dias agitados vêm em sequência), por isso é bem mais "
        "previsível que o sinal do preço. O erro do modelo costuma cair em relação aos "
        "últimos 20 dias porque ele corrige o nível (a volatilidade tende a voltar à média), "
        "mas a correlação com o que veio quase não melhora. Sem alavancagem (no máximo 100%)."
    )


def secao_aprendizado(dados, taxa_livre_de_risco):
    st.subheader("Aprendizado de máquina honesto")
    st.warning(
        "Aprendizado de máquina aumenta muito o risco de overfitting. Aqui o modelo sempre "
        "treina só com o passado e é medido contra uma previsão ingênua. É normal ele não vencer."
    )
    aba_dia, aba_barreira, aba_vol = st.tabs(
        ["Sinal do dia", "Barreira tripla e meta-rotulagem", "Volatilidade"]
    )
    with aba_dia:
        _ml_sinal_do_dia(dados, taxa_livre_de_risco)
    with aba_barreira:
        _ml_barreira_e_meta(dados, taxa_livre_de_risco)
    with aba_vol:
        _ml_volatilidade(dados, taxa_livre_de_risco)


def pagina_aprendizado():
    cabecalho_da_pagina("aprendizado")
    if not exigir_pagina("aprendizado"):
        return
    c = carregar_contexto()
    secao_aprendizado(c.dados, c.taxa_livre_de_risco)
