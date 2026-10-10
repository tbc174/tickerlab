"""Motor de backtest vetorizado: transforma uma posição desejada em resultado.

A regra de ouro está em `executar_backtest`: a posição que rende no dia t foi decidida no
fim do dia t-1 (`shift(1)`). Sem isso o backtest "olha o futuro" e engana.
"""

from dataclasses import dataclass

import pandas as pd

CUSTO_PADRAO_POR_OPERACAO = 0.0005  # 0,05% do valor negociado, por compra ou venda


@dataclass(frozen=True)
class ResultadoBacktest:
    """Tudo o que sai de um backtest, pronto para métricas e gráficos."""

    posicao: pd.Series  # fração do capital comprada em cada dia (0 a 1)
    retorno: pd.Series  # retorno diário da estratégia, já descontados os custos
    curva_de_capital: pd.Series  # R$ 1 investido no começo vira quanto (começa em 1)
    # uma linha por operação: entrada, saída, dias, retorno, aberta
    operacoes: pd.DataFrame
    giro: float  # soma das mudanças de posição (1 compra + 1 venda = 2)


COLUNAS_DAS_OPERACOES = ["entrada", "saida", "dias", "retorno", "aberta"]


def _extrair_operacoes(posicao: pd.Series, retorno: pd.Series) -> pd.DataFrame:
    """Uma operação é um trecho seguido de dias com posição. O custo da saída entra nela."""
    em_posicao = posicao > 0
    grupo = (em_posicao != em_posicao.shift(fill_value=False)).cumsum()
    linhas = []
    for _, trecho in posicao[em_posicao].groupby(grupo[em_posicao]):
        primeira, ultima = trecho.index[0], trecho.index[-1]
        posicao_da_ultima = posicao.index.get_loc(ultima)
        aberta = posicao_da_ultima == len(posicao) - 1
        # o dia da venda (primeiro dia sem posição) carrega o custo da saída
        fim = ultima if aberta else posicao.index[posicao_da_ultima + 1]
        retorno_da_operacao = (1 + retorno.loc[primeira:fim]).prod() - 1
        linhas.append(
            {
                "entrada": primeira,
                "saida": ultima,
                "dias": len(trecho),
                "retorno": retorno_da_operacao,
                "aberta": bool(aberta),
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_DAS_OPERACOES)


def executar_backtest(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> ResultadoBacktest:
    """Simula a estratégia.

    `posicao_desejada` é a decisão tomada no FIM de cada dia (0 = caixa, 1 = tudo comprado).
    A posição que de fato rende em um dia é a decidida no dia anterior.
    """
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    if fechamento.empty:
        raise ValueError("Não há preços para simular.")
    if not fechamento.index.equals(posicao_desejada.index):
        raise ValueError("Preços e posição precisam ter as mesmas datas.")
    if posicao_desejada.isna().any() or not posicao_desejada.between(0, 1).all():
        raise ValueError(
            "A posição desejada deve ficar entre 0 e 1, sem valores vazios."
        )

    retorno_do_ativo = fechamento.pct_change().fillna(0.0)
    posicao = posicao_desejada.shift(1, fill_value=0.0)  # NÃO olha o futuro
    mudanca = posicao.diff().abs().fillna(posicao.abs())  # entrar também custa
    retorno = posicao * retorno_do_ativo - mudanca * custo_por_operacao
    curva = (1 + retorno).cumprod()
    return ResultadoBacktest(
        posicao=posicao,
        retorno=retorno,
        curva_de_capital=curva,
        operacoes=_extrair_operacoes(posicao, retorno),
        giro=float(mudanca.sum()),
    )
