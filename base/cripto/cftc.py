"""Posições nos futuros de Bitcoin da CME, do relatório "Traders in Financial Futures" (TFF) da
CFTC (base de cripto, série 1, PR 3).

O relatório traz, toda semana, quantos contratos cada tipo de participante tinha comprados e
vendidos na terça-feira. Usamos dois tipos: **gestores** ("asset managers": fundos e
institucionais) e **alavancados** ("leveraged funds": fundos de hedge e operadores). A fonte é obra
do governo dos EUA (domínio público); citar a CFTC. A regra de quando o número passa a valer e as
paralisações estão em `base/commodities/cftc_cot.py`, comum ao café e aos outros agro.
"""

import pandas as pd

from base.commodities.cftc_cot import (
    EXCECOES_DE_DIVULGACAO,
    divulgado_em,
    ler_relatorio,
)

__all__ = ["EXCECOES_DE_DIVULGACAO", "divulgado_em", "endereco_do_ano", "ler_tff"]

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


def endereco_do_ano(ano: int) -> str:
    """O arquivo anual do TFF, só futuros, em texto."""
    return ENDERECO.format(ano=ano)


def ler_tff(conteudo_zip: bytes) -> pd.DataFrame:
    """Uma linha por relatório e contrato de Bitcoin da CME, com `divulgado_em`."""
    return ler_relatorio(conteudo_zip, COLUNAS, CONTRATOS)
