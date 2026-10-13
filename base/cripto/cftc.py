"""Posições nos futuros de Bitcoin da CME, do relatório "Traders in Financial Futures" (TFF) da
CFTC (base de cripto, série 1, PR 3).

O relatório traz, toda semana, quantos contratos cada tipo de participante tinha comprados e
vendidos na terça-feira. Usamos dois tipos: **gestores** ("asset managers": fundos e
institucionais) e **alavancados** ("leveraged funds": fundos de hedge e operadores). A fonte é obra
do governo dos EUA (domínio público); citar a CFTC.

**Quando o número passa a valer:** a CFTC divulga na sexta às 15h30 de Nova York, mas feriados
empurram para a segunda, e as paralisações do governo dos EUA atrasaram semanas (dez/2018–jan/2019 e
out–nov/2025). Para nunca usar um número antes de ele existir, a regra é **a segunda-feira seguinte
ao relatório de terça, às 15h30 de Nova York**; os atrasos maiores entram em
`EXCECOES_DE_DIVULGACAO`, com a data do calendário da CFTC.
"""

import io
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

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
NOVA_YORK = ZoneInfo("America/New_York")
HORA_DA_DIVULGACAO = time(15, 30)
# da terça do relatório até a segunda seguinte
DIAS_ATE_VALER = 6


def _as_15h30_de_nova_york(dia: date) -> datetime:
    return datetime.combine(dia, HORA_DA_DIVULGACAO, tzinfo=NOVA_YORK).astimezone(UTC)


# Paralisação de out–nov/2025: calendário de recuperação da CFTC (comunicado 9147-25, de
# 09/12/2025, e a atualização de 19/12/2025, que levou o dado de 23/12 para 31/12). Data do dado:
# data em que saiu. Vale no dia seguinte (um dia de folga, caso a publicação tenha escorregado).
_PARALISACAO_2025 = {
    date(2025, 9, 30): date(2025, 11, 19),
    date(2025, 10, 7): date(2025, 11, 21),
    date(2025, 10, 14): date(2025, 11, 25),
    date(2025, 10, 21): date(2025, 12, 2),
    date(2025, 10, 28): date(2025, 12, 5),
    date(2025, 11, 4): date(2025, 12, 9),
    date(2025, 11, 10): date(2025, 12, 10),
    date(2025, 11, 18): date(2025, 12, 12),
    date(2025, 11, 25): date(2025, 12, 15),
    date(2025, 12, 2): date(2025, 12, 17),
    date(2025, 12, 9): date(2025, 12, 19),
    date(2025, 12, 16): date(2025, 12, 23),
    date(2025, 12, 23): date(2025, 12, 31),
}
# Paralisação de dez/2018–jan/2019: a CFTC só publicou a regra ("um relatório na terça e outro na
# sexta até ficar em dia", comunicado 7864-19) e previu ficar em dia em 08/03/2019. Sem a data de
# cada relatório, todos os atrasados valem a partir de 15/03/2019: perde semanas, nunca adianta.
_INICIO_DA_PARALISACAO_2019 = date(2018, 12, 19)
_FIM_DA_PARALISACAO_2019 = date(2019, 3, 5)
_VALE_DEPOIS_DA_PARALISACAO_2019 = date(2019, 3, 15)


def _excecoes() -> dict[date, datetime]:
    excecoes = {
        dado: _as_15h30_de_nova_york(saiu + timedelta(days=1))
        for dado, saiu in _PARALISACAO_2025.items()
    }
    dia = _INICIO_DA_PARALISACAO_2019
    while dia <= _FIM_DA_PARALISACAO_2019:
        excecoes[dia] = _as_15h30_de_nova_york(_VALE_DEPOIS_DA_PARALISACAO_2019)
        dia += timedelta(days=1)
    return excecoes


# relatório (data do dado): desde quando vale, nas paralisações do governo dos EUA
EXCECOES_DE_DIVULGACAO: dict[date, datetime] = _excecoes()


def endereco_do_ano(ano: int) -> str:
    """O arquivo anual do TFF, só futuros, em texto."""
    return ENDERECO.format(ano=ano)


def divulgado_em(
    relatorio: date, excecoes: dict[date, datetime] = EXCECOES_DE_DIVULGACAO
) -> datetime:
    """Desde quando o relatório desta terça pode ser usado (em UTC)."""
    if relatorio in excecoes:
        return excecoes[relatorio]
    return _as_15h30_de_nova_york(relatorio + timedelta(days=DIAS_ATE_VALER))


def ler_tff(conteudo_zip: bytes) -> pd.DataFrame:
    """Uma linha por relatório e contrato de Bitcoin da CME, com `divulgado_em`."""
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as arquivo:
        texto = arquivo.read(arquivo.namelist()[0])
    tabela = pd.read_csv(
        io.BytesIO(texto),
        usecols=list(COLUNAS),
        dtype={"CFTC_Contract_Market_Code": str},
        encoding="latin-1",
        skipinitialspace=True,
    ).rename(columns=COLUNAS)
    tabela["codigo"] = tabela["codigo"].str.strip()
    tabela = tabela[tabela["codigo"].isin(CONTRATOS)].copy()
    tabela["contrato"] = tabela.pop("codigo").map(CONTRATOS)
    tabela["relatorio"] = pd.to_datetime(tabela["relatorio"]).dt.date
    tabela["divulgado_em"] = tabela["relatorio"].map(divulgado_em)
    return tabela.sort_values(["relatorio", "contrato"]).reset_index(drop=True)
