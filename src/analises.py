"""O que cada página de análise mostra, montado a partir dos indicadores.

A tela do Streamlit e a API de leitura chamam as mesmas funções daqui, então os números são os
mesmos nos dois lugares (ADR 0044). Entradas e saídas em tipos simples: números, datas e séries do
pandas só onde a página desenha um gráfico.
"""

from dataclasses import dataclass

import pandas as pd

from src import indicadores as ind
from src.comparacao import (
    alinhar_fechamentos,
    montar_tabela_comparativa,
    rebasear_para_100,
)

MIN_DIAS_PARA_ANALISE = 20  # com menos retornos que isso, os números não dizem nada


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
        retorno_anualizado=ind.retorno_anualizado_para_mostrar(retorno),
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


# --- como a visão geral mostra o painel (o app em React lê daqui; há teste contra a tela) ---


@dataclass(frozen=True)
class ItemDoPainel:
    """Um número do painel: o campo de `PainelDeNumeros`, o rótulo, o "?" e o formato."""

    campo: str
    rotulo: (
        str  # pode ter {data} (o `campo_da_data` em dd/mm/aaaa) e {confianca} (do VaR)
    )
    termo: str  # o termo do glossário que explica o número
    formato: str  # "pct", "pct_com_sinal" ou "decimal" (src/formatos.py)
    grupo: str
    campo_da_data: str | None = None


RETORNO_E_RISCO = "Retorno e risco"
CONSISTENCIA = "Consistência e dias extremos"
ITENS_DO_PAINEL = (
    ItemDoPainel("retorno_total", "Retorno total", "Retorno acumulado", "pct_com_sinal", RETORNO_E_RISCO),
    ItemDoPainel("retorno_anualizado", "Retorno anualizado", "Retorno anualizado", "pct_com_sinal", RETORNO_E_RISCO),
    ItemDoPainel("volatilidade_anual", "Volatilidade anual", "Volatilidade", "pct", RETORNO_E_RISCO),
    ItemDoPainel("maior_queda", "Maior queda (drawdown)", "Drawdown", "pct", RETORNO_E_RISCO),
    ItemDoPainel("sharpe", "Índice de Sharpe", "Índice de Sharpe", "decimal", CONSISTENCIA),
    ItemDoPainel("melhor_dia", "Melhor dia ({data})", "Melhor e pior dia", "pct_com_sinal", CONSISTENCIA, "data_do_melhor_dia"),
    ItemDoPainel("pior_dia", "Pior dia ({data})", "Melhor e pior dia", "pct_com_sinal", CONSISTENCIA, "data_do_pior_dia"),
    ItemDoPainel("dias_de_alta", "Dias de alta", "Dias de alta", "pct", CONSISTENCIA),
    ItemDoPainel("var", "Perda de um dia ruim (VaR {confianca}%)", "Perda de um dia ruim (VaR)", "pct", CONSISTENCIA),
)  # fmt: skip
LEGENDA_DO_PAINEL = "Passe o mouse no ? de cada número para ver o que ele significa."
# a frase do CVaR, embaixo do painel ({confianca} e {cvar} já formatado)
FRASE_DO_CVAR = (
    "Perda média nos piores dias (CVaR {confianca}%): {cvar}. Quando o dia foi pior que o VaR, "
    "esta foi a perda média. Estimativa feita com o passado, não um limite de perda."
)


def aviso_janela_curta(janela: int) -> str:
    """Quando o período não tem dias para a volatilidade móvel da janela escolhida."""
    return (
        f"O período é curto demais para uma janela de {janela} dias. "
        "Escolha uma janela menor ou um período maior."
    )


LEGENDA_DO_MAPA_MENSAL = (
    "O primeiro e o último mês do período podem estar incompletos. "
    "A última linha mostra a média de cada mês ao longo dos anos "
    "(com poucos anos de dados, isso pode ser só coincidência)."
)


def aviso_poucos_dias_em_comum(dias_em_comum: int) -> str:
    """Quando os ativos comparados têm poucos pregões em comum."""
    return (
        f"Só há {dias_em_comum} dias em comum entre esses ativos, e são necessários "
        f"mais de {MIN_DIAS_PARA_ANALISE}. Tente um período mais longo ou outros ativos."
    )


def nota_da_comparacao(dias_em_comum: int, dias_descartados: int) -> str:
    """Como a comparação foi feita (dias em comum, nada inventado, moedas diferentes)."""
    return (
        f"Comparação feita em {dias_em_comum} dias em comum. "
        f"{dias_descartados} dias foram descartados porque algum ativo não tinha preço neles "
        "(feriados diferentes), sem preencher nem estimar nada. Por isso os números daqui podem "
        "diferir um pouco dos das outras abas, que usam todos os dias do ativo. "
        "As moedas diferentes (R$ e US$) não atrapalham, porque comparamos a variação "
        "percentual, não os preços."
    )


def aviso_da_origem(origem: str, ate: str | None) -> str | None:
    """O aviso quando os preços não são os mais recentes do Yahoo ("cache_antigo" ou "exemplo")."""
    if origem == "cache_antigo":
        return (
            "Não consegui atualizar com o Yahoo Finance agora. Estes são os preços que o app "
            f"tinha guardado, até {ate}."
        )
    if origem == "exemplo":
        return (
            f"Estes são dados de exemplo guardados no projeto, até {ate}, "
            "e não os mais recentes do Yahoo Finance."
        )
    return None


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


@dataclass(frozen=True)
class Comparacao:
    """Ativos lado a lado nos dias em que todos têm preço (sem preencher nem estimar nada)."""

    dias_em_comum: int
    dias_descartados: int  # feriados diferentes: algum ativo sem preço no dia
    base_100: pd.DataFrame | None  # todos começando em 100; None se o período for curto
    tabela: pd.DataFrame | None  # os números de cada ativo; None se o período for curto

    @property
    def suficiente(self) -> bool:
        return self.base_100 is not None


def comparacao_de_ativos(
    fechamentos: dict[str, pd.Series], taxa_livre_de_risco: float
) -> Comparacao:
    """O que a página Comparar mostra. Com até MIN_DIAS_PARA_ANALISE dias em comum, só as contagens."""
    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) <= MIN_DIAS_PARA_ANALISE:
        return Comparacao(len(alinhado), descartados, None, None)
    return Comparacao(
        dias_em_comum=len(alinhado),
        dias_descartados=descartados,
        base_100=rebasear_para_100(alinhado),
        tabela=montar_tabela_comparativa(alinhado, taxa_livre_de_risco),
    )
