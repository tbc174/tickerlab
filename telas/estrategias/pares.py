"""Avançado (Pro): operações em pares.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import numpy as np
import pandas as pd
import streamlit as st

from src import graficos
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.comparacao import alinhar_fechamentos, interpretar_tickers
from src.dados import DadosIndisponiveisError
from src.metricas import resumir_desempenho
from src.pares import MAX_ATIVOS_PARA_PARES, procurar_pares, simular_par
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    carregar_dados,
    formatar_metrica,
    mostrar_grafico,
)
from telas.conta.assinatura import exigir_pagina
from telas.dados_da_conta import oferecer_salvar_simulacao

PARES_PADRAO = "ITUB4, BBDC4, BBAS3, PETR4, PETR3"


def _tabela_de_pares(tabela):
    exibicao = pd.DataFrame(index=tabela.index)
    exibicao["Correlação"] = [
        formatar_metrica("Sharpe", v) for v in tabela["Correlação"]
    ]
    exibicao["Beta"] = [formatar_metrica("Sharpe", v) for v in tabela["Beta"]]
    exibicao["ADF no treino"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no treino"]
    ]
    exibicao["Meia-vida (dias)"] = [
        "—" if not np.isfinite(v) else f"{v:.0f}" for v in tabela["Meia-vida (dias)"]
    ]
    exibicao["Ligado no treino?"] = [
        "Sim" if v else "Não" for v in tabela["Cointegrado no treino"]
    ]
    exibicao["ADF no teste"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no teste"]
    ]
    exibicao["Continuou no teste?"] = [
        "Sim" if v else "Não" for v in tabela["Continuou no teste"]
    ]
    return exibicao


def secao_pares(periodo, taxa_livre_de_risco):
    st.subheader("Pairs trading: apostar que dois ativos voltam a andar juntos")
    st.caption(ajuda_do("Pairs trading"))
    st.warning(
        "Este é um desafio educativo. A perna vendida exige aluguel de ações, que tem custo e "
        "nem sempre está disponível; esse custo não entra na simulação. Resultado do passado "
        "não garante nada."
    )
    with st.container(border=True):
        texto = st.text_input(
            f"Ativos (2 a {MAX_ATIVOS_PARA_PARES}, separados por vírgula)",
            value=PARES_PADRAO,
            key="pares_ativos",
            help="O app testa todos os pares possíveis da lista.",
        )
        c1, c2 = st.columns(2)
        fracao = c1.slider(
            "Parte do período usada para estimar (treino)",
            0.3,
            0.8,
            0.5,
            0.05,
            key="pares_treino",
            help="A relação entre os ativos é estimada só nesta parte; a negociação acontece no resto.",
        )
        custo = (
            c2.number_input(
                "Custo por operação (%)",
                0.0,
                2.0,
                CUSTO_PADRAO_POR_OPERACAO * 100,
                0.01,
                format="%.2f",
                key="pares_custo",
            )
            / 100
        )
    tickers = interpretar_tickers(texto)
    if not 2 <= len(tickers) <= MAX_ATIVOS_PARA_PARES:
        st.info(
            f"Escolha de 2 a {MAX_ATIVOS_PARA_PARES} ativos (agora são {len(tickers)})."
        )
        return
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, _ = alinhar_fechamentos(fechamentos)
    try:
        tabela = procurar_pares(alinhado, fracao)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown("**Todos os pares da lista**")
    st.dataframe(_tabela_de_pares(tabela), width="stretch")
    sobreviventes = int(tabela["Cointegrado no treino"].sum())
    continuaram = int(
        (tabela["Cointegrado no treino"] & tabela["Continuou no teste"]).sum()
    )
    st.caption(
        f"{len(tabela)} pares testados; {sobreviventes} pareceram ligados no treino e "
        f"{continuaram} continuaram ligados no teste. ADF abaixo de −3,34 indica relação "
        "(valor aproximado de Engle-Granger a 5%). Ao testar muitos pares, uns 5% parecem "
        "ligados só por sorte: por isso a conferência no teste."
    )

    par = st.selectbox("Par para simular", list(tabela.index), key="pares_escolhido")
    a, b = par.split(" × ")
    c1, c2, c3, c4 = st.columns(4)
    entrada = c1.slider(
        "Entra com |z| acima de", 1.0, 3.0, 2.0, 0.1, key="pares_entrada"
    )
    saida = c2.slider("Sai com |z| abaixo de", 0.0, 1.0, 0.5, 0.1, key="pares_saida")
    stop = c3.slider("Stop com |z| acima de", 3.0, 6.0, 4.0, 0.5, key="pares_stop")
    janela = c4.slider("Janela do z-score (dias)", 20, 120, 60, 5, key="pares_janela")
    try:
        r = simular_par(
            alinhado[a], alinhado[b], fracao, entrada, saida, stop, janela, custo
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    bt = r.backtest
    numeros = resumir_desempenho(
        bt.retorno, bt.posicao, bt.operacoes, taxa_livre_de_risco
    )
    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes,
        ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"],
        strict=True,
    ):
        coluna.metric(metrica, formatar_metrica(metrica, numeros[metrica]))
    oferecer_salvar_simulacao(
        "pares",
        f"Par {a} × {b} · {periodo}",
        {m: formatar_metrica(m, v) for m, v in numeros.items()},
        f"{alinhado.index[-1]:%d/%m/%Y}",
    )
    meia = r.treino.meia_vida
    st.caption(
        f"Relação estimada no treino: log {a} = {formatar_metrica('Sharpe', r.treino.beta)} × log {b} + constante. "
        f"Meia-vida do spread no treino: {'sem volta' if not np.isfinite(meia) else f'{meia:.0f} dias'}. "
        f"ADF: {formatar_metrica('Sharpe', r.treino.adf)} no treino e "
        f"{formatar_metrica('Sharpe', r.teste.adf)} no teste "
        f"({'a relação continuou' if r.teste.cointegrado else 'a relação NÃO se confirmou no teste'})."
    )
    mostrar_grafico(
        graficos.criar_grafico_z_do_par(r.z, r.lado, entrada, stop, r.inicio_do_teste)
    )
    teste_a = alinhado[a].loc[r.inicio_do_teste :]
    teste_b = alinhado[b].loc[r.inicio_do_teste :]
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {
                f"Par {a} × {b}": bt.curva_de_capital,
                f"Comprar e segurar {a}": teste_a / teste_a.iloc[0],
                f"Comprar e segurar {b}": teste_b / teste_b.iloc[0],
            },
            10_000.0,
            destaque=f"Par {a} × {b}",
        )
    )
    st.caption(
        "O par é neutro ao mercado: não depende de os preços subirem. Compare o retorno e a "
        "queda com os dois ativos sozinhos, no mesmo período de teste. Se o ADF do teste não "
        "confirma a relação, o lucro (se houve) provavelmente foi sorte."
    )


def pagina_pares():
    cabecalho_da_pagina("pares")
    if not exigir_pagina("pares"):
        return
    c = carregar_contexto()
    secao_pares(c.periodo, c.taxa_livre_de_risco)
