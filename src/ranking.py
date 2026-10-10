"""Ranking: roda todas as estratégias do registro no mesmo ativo, com os valores padrão.

Rodar muitas estratégias e olhar a melhor é exatamente o que gera o *data snooping* (achar um
vencedor por sorte). Por isso o ranking traz, ao lado do Sharpe, o Sharpe deflacionado (que
desconta o número de estratégias testadas) e o teste contra o acaso.
"""

import numpy as np
import pandas as pd

from src.acaso import calcular_sharpe_deflacionado, testar_contra_o_acaso
from src.backtest import ResultadoBacktest, executar_backtest
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.metricas import resumir_desempenho
from src.protecoes import Protecoes, aplicar_protecoes

COLUNAS_DO_RANKING = [
    "Grupo",
    "Retorno total",
    "Retorno anualizado",
    "Volatilidade anual",
    "Índice de Sharpe",
    "Maior queda",
    "Exposição média",
    "Operações",
    "Chance de não ser sorte",
    "p-valor (acaso)",
]


def montar_ranking(
    dados: pd.DataFrame,
    custo_por_operacao: float,
    taxa_livre_de_risco: float = 0.0,
    tentativas_extras: int = 0,
    sorteios: int = 300,
    protecoes: Protecoes | None = None,
) -> tuple[pd.DataFrame, dict[str, ResultadoBacktest]]:
    """Tabela ordenada pelo Sharpe (do maior ao menor) e o resultado completo de cada estratégia."""
    resultados: dict[str, ResultadoBacktest] = {}
    posicoes: dict[str, pd.Series] = {}
    for nome in ESTRATEGIAS:
        posicao = gerar_posicao(nome, dados)
        if protecoes is not None:
            posicao = aplicar_protecoes(dados, posicao, protecoes)
        posicoes[nome] = posicao
        resultados[nome] = executar_backtest(
            dados["Close"], posicao, custo_por_operacao
        )

    retornos = pd.DataFrame({nome: r.retorno for nome, r in resultados.items()})
    linhas = {}
    for nome, resultado in resultados.items():
        numeros = resumir_desempenho(
            resultado.retorno,
            resultado.posicao,
            resultado.operacoes,
            taxa_livre_de_risco,
        )
        try:
            chance = calcular_sharpe_deflacionado(
                resultado.retorno, retornos, tentativas_extras, taxa_livre_de_risco
            ).probabilidade
        except ValueError:
            chance = np.nan
        try:
            p_valor = testar_contra_o_acaso(
                dados["Close"],
                posicoes[nome],
                custo_por_operacao,
                taxa_livre_de_risco,
                sorteios,
            ).p_valor
        except ValueError:  # não operou, ou poucos dados
            p_valor = np.nan
        linhas[nome] = {
            "Grupo": ESTRATEGIAS[nome].grupo,
            "Retorno total": numeros["Retorno total"],
            "Retorno anualizado": numeros["Retorno anualizado"],
            "Volatilidade anual": numeros["Volatilidade anual"],
            "Índice de Sharpe": numeros["Índice de Sharpe"],
            "Maior queda": numeros["Maior queda"],
            "Exposição média": numeros["Exposição média"],
            "Operações": numeros["Operações"],
            "Chance de não ser sorte": chance,
            "p-valor (acaso)": p_valor,
        }
    tabela = pd.DataFrame.from_dict(linhas, orient="index")[COLUNAS_DO_RANKING]
    tabela = tabela.sort_values("Índice de Sharpe", ascending=False, na_position="last")
    return tabela, resultados
