"""Posições nos futuros de Bitcoin da CME, do relatório "Traders in Financial Futures" (TFF) da
CFTC (base de cripto, série 1, PR 3).

O relatório traz, toda semana, quantos contratos cada tipo de participante tinha comprados e
vendidos na terça-feira. Usamos dois tipos: **gestores** ("asset managers": fundos e
institucionais) e **alavancados** ("leveraged funds": fundos de hedge e operadores). A fonte é obra
do governo dos EUA (domínio público); citar a CFTC. A regra de quando o número passa a valer e as
paralisações estão em `base/commodities/cftc_cot.py`, comum ao café e aos outros agro.
"""

import io
from datetime import date, timedelta

import pandas as pd

from base.commodities.cftc_cot import (
    EXCECOES_DE_DIVULGACAO,
    NOVA_YORK,
    divulgado_em,
    ler_relatorio,
    ler_texto_do_zip,
)

__all__ = [
    "COLUNAS_DO_TFF_INTEIRO",
    "EXCECOES_DE_DIVULGACAO",
    "divulgado_em",
    "endereco_do_ano",
    "ler_tff",
    "ler_tff_inteiro",
    "publicado_em",
]

ENDERECO = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{ano}.zip"
# códigos de contrato da CFTC (o nome do mercado muda com o tempo; o código não)
CONTRATOS = {"133741": "bitcoin", "133742": "micro_bitcoin"}
COLUNAS = {
    "Report_Date_as_YYYY-MM-DD": "relatorio",
    "CFTC_Contract_Market_Code": "codigo",
    "Open_Interest_All": "contratos_em_aberto",
    "Asset_Mgr_Positions_Long_All": "gestores_comprados",
    "Asset_Mgr_Positions_Short_All": "gestores_vendidos",
    "Lev_Money_Positions_Long_All": "alavancados_comprados",
    "Lev_Money_Positions_Short_All": "alavancados_vendidos",
}
# TFF inteiro (linha 630, A2): todas as categorias de participante de todos os contratos do relatório.
# cabeçalho da CFTC → coluna da base; "dealers" = intermediários, "gestores" = asset managers,
# "alavancados" = leveraged funds, "outros" = outros reportáveis; o que sobra é "não reportável"
COLUNAS_DO_TFF_INTEIRO = {
    "Report_Date_as_YYYY-MM-DD": "relatorio",
    "CFTC_Contract_Market_Code": "codigo",
    "Market_and_Exchange_Names": "mercado",
    "CFTC_Market_Code": "bolsa",
    "Open_Interest_All": "contratos_em_aberto",
    "Dealer_Positions_Long_All": "dealers_comprados",
    "Dealer_Positions_Short_All": "dealers_vendidos",
    "Dealer_Positions_Spread_All": "dealers_spread",
    "Asset_Mgr_Positions_Long_All": "gestores_comprados",
    "Asset_Mgr_Positions_Short_All": "gestores_vendidos",
    "Asset_Mgr_Positions_Spread_All": "gestores_spread",
    "Lev_Money_Positions_Long_All": "alavancados_comprados",
    "Lev_Money_Positions_Short_All": "alavancados_vendidos",
    "Lev_Money_Positions_Spread_All": "alavancados_spread",
    "Other_Rept_Positions_Long_All": "outros_comprados",
    "Other_Rept_Positions_Short_All": "outros_vendidos",
    "Other_Rept_Positions_Spread_All": "outros_spread",
    "NonRept_Positions_Long_All": "nao_reportaveis_comprados",
    "NonRept_Positions_Short_All": "nao_reportaveis_vendidos",
}
_TEXTOS_DO_TFF = ("relatorio", "codigo", "mercado", "bolsa")
# da terça do relatório até a sexta em que a CFTC publica
DIAS_ATE_A_SEXTA = 3


def endereco_do_ano(ano: int) -> str:
    """O arquivo anual do TFF, só futuros, em texto."""
    return ENDERECO.format(ano=ano)


def ler_tff(conteudo_zip: bytes) -> pd.DataFrame:
    """Uma linha por relatório e contrato de Bitcoin da CME, com `divulgado_em`."""
    return ler_relatorio(conteudo_zip, COLUNAS, CONTRATOS)


def publicado_em(relatorio: date) -> date:
    """O dia em que a CFTC publicou o relatório desta terça: a sexta seguinte, ou, nas paralisações,
    o dia do calendário de recuperação (o `divulgado_em` guarda um dia de folga depois dele)."""
    if relatorio in EXCECOES_DE_DIVULGACAO:
        chegou = EXCECOES_DE_DIVULGACAO[relatorio].astimezone(NOVA_YORK).date()
        return max(
            relatorio + timedelta(days=DIAS_ATE_A_SEXTA), chegou - timedelta(days=1)
        )
    return relatorio + timedelta(days=DIAS_ATE_A_SEXTA)


def ler_tff_inteiro(conteudo_zip: bytes) -> pd.DataFrame:
    """Uma linha por relatório e contrato do TFF, de todos os mercados, com as cinco categorias.

    `relatorio` é a terça a que as posições se referem; `publicado_em`, o dia da publicação (sexta);
    `disponivel_em` (UTC) é o `divulgado_em`: nunca antes da publicação (a regra conservadora empurra
    feriados para a segunda). A chave é `relatorio` + `codigo`. Posição vazia ("." na fonte) fica nula.
    """
    tabela = pd.read_csv(
        io.BytesIO(ler_texto_do_zip(conteudo_zip)),
        usecols=list(COLUNAS_DO_TFF_INTEIRO),
        dtype={
            nome: str
            for nome, novo in COLUNAS_DO_TFF_INTEIRO.items()
            if novo in _TEXTOS_DO_TFF
        },
        encoding="latin-1",
        skipinitialspace=True,
    ).rename(columns=COLUNAS_DO_TFF_INTEIRO)
    for coluna in _TEXTOS_DO_TFF[1:]:
        tabela[coluna] = tabela[coluna].str.strip()
    for coluna in tabela.columns.difference(list(_TEXTOS_DO_TFF)):
        tabela[coluna] = pd.to_numeric(tabela[coluna], errors="coerce").astype("Int64")
    tabela["relatorio"] = pd.to_datetime(tabela["relatorio"]).dt.date
    tabela["publicado_em"] = tabela["relatorio"].map(publicado_em)
    tabela["disponivel_em"] = tabela["relatorio"].map(divulgado_em)
    return tabela.sort_values(["relatorio", "codigo"]).reset_index(drop=True)
