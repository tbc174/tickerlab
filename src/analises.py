"""O que cada página de análise mostra, montado a partir dos indicadores.

A tela do Streamlit e a API de leitura chamam as mesmas funções daqui, então os números são os
mesmos nos dois lugares (ADR 0044). Entradas e saídas em tipos simples: números, datas e séries do
pandas só onde a página desenha um gráfico.
"""

from dataclasses import dataclass

import pandas as pd

from src import indicadores as ind


@dataclass(frozen=True)
class PainelDeNumeros:
    """Os números da visão geral de um ativo (frações: 0,12 = 12%)."""

    retorno_total: float
    retorno_anualizado: float
    volatilidade_anual: float
    maior_queda: float
    sharpe: float
    data_do_melhor_dia: pd.Timestamp
    melhor_dia: float
    data_do_pior_dia: pd.Timestamp
    pior_dia: float
    dias_de_alta: float
    confianca_do_var: int  # em %: 95 = VaR de 95%
    var: float
    cvar: float


def painel_de_numeros(
    fechamento: pd.Series,
    retorno: pd.Series,
    taxa_livre_de_risco: float,
    confianca_do_var: int,
) -> PainelDeNumeros:
    """Retorno, risco, dias extremos e a perda de um dia ruim, do jeito que a visão geral mostra."""
    data_melhor, melhor_dia = ind.encontrar_melhor_dia(retorno)
    data_pior, pior_dia = ind.encontrar_pior_dia(retorno)
    confianca = confianca_do_var / 100
    return PainelDeNumeros(
        retorno_total=ind.calcular_retorno_acumulado(retorno).iloc[-1],
        retorno_anualizado=ind.calcular_retorno_anualizado(retorno),
        volatilidade_anual=ind.calcular_volatilidade_anual(retorno),
        maior_queda=ind.calcular_drawdown(fechamento).min(),
        sharpe=ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco),
        data_do_melhor_dia=data_melhor,
        melhor_dia=melhor_dia,
        data_do_pior_dia=data_pior,
        pior_dia=pior_dia,
        dias_de_alta=ind.calcular_percentual_dias_positivos(retorno),
        confianca_do_var=confianca_do_var,
        var=ind.calcular_var_historico(retorno, confianca),
        cvar=ind.calcular_cvar_historico(retorno, confianca),
    )


@dataclass(frozen=True)
class RiscoAoLongoDoTempo:
    """A queda desde o topo dia a dia, a pior delas e a volatilidade numa janela móvel."""

    drawdown: pd.Series
    pior_drawdown: ind.PiorDrawdown
    janela: int  # dias da volatilidade móvel
    volatilidade_movel: pd.Series


def risco_ao_longo_do_tempo(
    fechamento: pd.Series, retorno: pd.Series, janela: int
) -> RiscoAoLongoDoTempo:
    """O que a página Risco mostra; a volatilidade móvel fica vazia se o período for curto."""
    return RiscoAoLongoDoTempo(
        drawdown=ind.calcular_drawdown(fechamento),
        pior_drawdown=ind.encontrar_pior_drawdown(fechamento),
        janela=janela,
        volatilidade_movel=ind.calcular_volatilidade_movel(retorno, janela),
    )


@dataclass(frozen=True)
class RetornoMensal:
    """O retorno de cada mês, a tabela ano × mês, o melhor e o pior mês e os meses de alta."""

    retornos: pd.Series
    tabela: pd.DataFrame
    mes_melhor: pd.Period
    melhor: float
    mes_pior: pd.Period
    pior: float
    meses_de_alta: float  # fração dos meses que fecharam no positivo


def retorno_mensal(retorno: pd.Series) -> RetornoMensal:
    """O que a página Retorno mensal mostra."""
    retornos = ind.calcular_retorno_mensal(retorno)
    (mes_melhor, melhor), (mes_pior, pior) = ind.encontrar_melhor_e_pior_mes(retornos)
    return RetornoMensal(
        retornos=retornos,
        tabela=ind.montar_tabela_retornos(retornos),
        mes_melhor=mes_melhor,
        melhor=melhor,
        mes_pior=mes_pior,
        pior=pior,
        meses_de_alta=ind.calcular_percentual_dias_positivos(retornos),
    )
