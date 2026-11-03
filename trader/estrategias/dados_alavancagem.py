"""Pernas sintéticas dos futuros para a alavancagem do núcleo (pré-registro v0.1, seção 7).

A base local não tem histórico do WIN nem do DI1 (o export do MT5 só tem BOVA11, ouro, S&P 500 e
dólar; a assinatura do Profit Ultra ficou para depois deste backtest). O que um futuro rende, sem
pôr dinheiro além da margem, é o que o ativo rende acima do CDI; então cada perna é um índice
menos o CDI:

- **WIN:** o BOVA11 em reais menos o CDI. Fica de fora a base de mercado do futuro (o quanto o WIN
  negocia acima ou abaixo do justo) e o descasamento entre o Ibovespa e o ETF: limitação declarada.
- **DI1:** um prefixado de prazo constante de 2 anos marcado todo dia no vértice de 2 anos da curva
  nominal do Tesouro Direto (acervo `curva_juros`, curva "nominal", desde 2005), menos o CDI. É o
  que a posição comprada no DI1 de janeiro mais perto de 2 anos rende, sem a base entre a curva do
  Tesouro e a da B3: limitação declarada.

Nada aqui decide nada: as taxas marcam o preço do dia; a decisão do núcleo vem da camada A1.
"""

from __future__ import annotations

import pandas as pd

from trader.estrategias import dados_p0_3

PRAZO_DO_DI1_EM_ANOS = 2.0
PREGOES_POR_ANO = dados_p0_3.PREGOES_POR_ANO
CURVA_NOMINAL = "nominal"


def indice_prefixado(
    taxa: pd.Series, prazo_anos: float = PRAZO_DO_DI1_EM_ANOS
) -> pd.Series:
    """Índice (começa em 100) de um título prefixado de prazo constante, sem cupom.

    Todo dia compra um título de `prazo_anos` na taxa de ontem e o vende hoje, com um pregão a
    menos de prazo, na taxa de hoje: carry mais o efeito da taxa ter mudado.
    """
    hoje = taxa.astype(float)
    ontem = hoje.shift(1)
    retorno = (1 + ontem) ** prazo_anos / (1 + hoje) ** (
        prazo_anos - 1 / PREGOES_POR_ANO
    ) - 1
    retorno.iloc[0] = 0.0
    return 100 * (1 + retorno).cumprod()


def excesso_do_win(bova11: pd.Series, cdi: pd.Series) -> pd.Series:
    """O que o WIN sintético rende por dia sobre o nocional: BOVA11 menos CDI (0 no 1º dia)."""
    retorno = bova11.sort_index().astype(float).pct_change(fill_method=None)
    excesso = retorno - cdi.reindex(retorno.index)
    excesso.iloc[0] = 0.0
    return excesso.rename("WIN")


def excesso_do_di1(
    curva: pd.DataFrame,
    cdi: pd.Series,
    datas: pd.DatetimeIndex,
    prazo_anos: float = PRAZO_DO_DI1_EM_ANOS,
) -> pd.Series:
    """O que o DI1 sintético rende por dia sobre o nocional: prefixado de 2 anos menos CDI.

    Dia sem curva mantém a taxa de ontem (rende só o carry). Falta de curva no começo é erro.
    """
    nominal = curva[curva["curva"] == CURVA_NOMINAL]
    if nominal.empty:
        raise ValueError("a tabela não tem a curva nominal")
    taxa = dados_p0_3.ao_calendario(
        dados_p0_3.ponto_da_curva(nominal, prazo_anos), datas
    )
    if taxa.isna().any():
        raise ValueError(
            f"curva nominal faltando no começo: {taxa.index[taxa.isna()][0].date()}"
        )
    retorno = indice_prefixado(taxa, prazo_anos).pct_change(fill_method=None)
    excesso = retorno - cdi.reindex(datas)
    excesso.iloc[0] = 0.0
    return excesso.rename("DI1")
