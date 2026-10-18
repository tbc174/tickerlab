"""Leitor comum dos relatórios semanais da CFTC (Commitments of Traders): quando o número passa a valer
e como abrir o arquivo anual.

Usado pelo TFF do Bitcoin (`base/cripto/cftc.py`) e pelo Disaggregated do café e dos outros agro
(`base/commodities/cftc_cot.py`). A fonte é obra do governo dos EUA (domínio público); citar a CFTC.

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


def divulgado_em(
    relatorio: date, excecoes: dict[date, datetime] = EXCECOES_DE_DIVULGACAO
) -> datetime:
    """Desde quando o relatório desta terça pode ser usado (em UTC)."""
    if relatorio in excecoes:
        return excecoes[relatorio]
    return _as_15h30_de_nova_york(relatorio + timedelta(days=DIAS_ATE_VALER))


def ler_texto_do_zip(conteudo_zip: bytes) -> bytes:
    """O texto do primeiro (e único) arquivo do zip anual da CFTC."""
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as arquivo:
        return arquivo.read(arquivo.namelist()[0])


def ler_relatorio(
    conteudo_zip: bytes, colunas: dict[str, str], contratos: dict[str, str]
) -> pd.DataFrame:
    """Uma linha por relatório e contrato pedido, com `divulgado_em`.

    `colunas` traduz o cabeçalho da CFTC para o nome da base (precisa ter a data do relatório como
    `relatorio` e o código do contrato como `codigo`); `contratos` traduz o código do mercado para o
    nome do contrato, e o que não está nele sai.
    """
    tabela = pd.read_csv(
        io.BytesIO(ler_texto_do_zip(conteudo_zip)),
        usecols=list(colunas),
        dtype={nome: str for nome, novo in colunas.items() if novo == "codigo"},
        encoding="latin-1",
        skipinitialspace=True,
    ).rename(columns=colunas)
    tabela["codigo"] = tabela["codigo"].str.strip()
    tabela = tabela[tabela["codigo"].isin(contratos)].copy()
    tabela["contrato"] = tabela.pop("codigo").map(contratos)
    tabela["relatorio"] = pd.to_datetime(tabela["relatorio"]).dt.date
    tabela["divulgado_em"] = tabela["relatorio"].map(divulgado_em)
    return tabela.sort_values(["relatorio", "contrato"]).reset_index(drop=True)


# --- Disaggregated: posição dos fundos no café e nos outros agro (PR 5 do plano do café) ---

FONTE = (
    "cftc-cot-disaggregated"  # o id da fonte no arquivista (`base/arquivo/fontes.py`)
)
ENDERECO_DO_ANO = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{ano}.zip"
# 2006 a 2016 vêm juntos num zip só: a CFTC não tem os anos 2006 a 2009 separados
ENDERECO_DO_HISTORICO = (
    "https://www.cftc.gov/files/dea/history/fut_disagg_txt_hist_2006_2016.zip"
)
PRIMEIRO_ANO_SEPARADO = 2017
# códigos conferidos no arquivo de 2026 (18/10/2026): código → (contrato da base, mercado)
CONTRATOS_AGRO: dict[str, tuple[str, str]] = {
    "083731": ("cafe-arabica", "Coffee C (ICE Futures U.S.)"),
    "080732": ("acucar", "Sugar No. 11 (ICE Futures U.S.)"),
    "005602": ("soja", "Soybeans (CBOT)"),
    "002602": ("milho", "Corn (CBOT)"),
    "057642": ("boi-gordo", "Live Cattle (CME)"),
    "033661": ("algodao", "Cotton No. 2 (ICE Futures U.S.)"),
}
# cabeçalho da CFTC → coluna da base (a CFTC escreve "Swap__" com dois sublinhados no short e no spread)
COLUNAS_DO_DISAGGREGATED = {
    "Report_Date_as_YYYY-MM-DD": "relatorio",
    "CFTC_Contract_Market_Code": "codigo",
    "Open_Interest_All": "open_interest",
    "Prod_Merc_Positions_Long_All": "producer_merchant_long",
    "Prod_Merc_Positions_Short_All": "producer_merchant_short",
    "Swap_Positions_Long_All": "swap_long",
    "Swap__Positions_Short_All": "swap_short",
    "Swap__Positions_Spread_All": "swap_spread",
    "M_Money_Positions_Long_All": "managed_money_long",
    "M_Money_Positions_Short_All": "managed_money_short",
    "M_Money_Positions_Spread_All": "managed_money_spread",
}
COLUNAS_AGRO = (
    "relatorio",
    "contrato",
    "open_interest",
    "producer_merchant_long",
    "producer_merchant_short",
    "swap_long",
    "swap_short",
    "swap_spread",
    "managed_money_long",
    "managed_money_short",
    "managed_money_spread",
    "disponivel_em",
)


def enderecos_do_disaggregated(hoje: date) -> list[str]:
    """Os arquivos do Disaggregated só de futuros: o histórico 2006–2016 e um zip por ano até `hoje`."""
    anos = range(PRIMEIRO_ANO_SEPARADO, hoje.year + 1)
    return [ENDERECO_DO_HISTORICO, *(ENDERECO_DO_ANO.format(ano=ano) for ano in anos)]


def ler_disaggregated(conteudo_zip: bytes) -> pd.DataFrame:
    """Uma linha por relatório e contrato agro, com a posição dos fundos e `disponivel_em`.

    `disponivel_em` é o dia **depois** da divulgação (`divulgado_em`): quem consulta "como estava em
    D" nunca vê o relatório da terça antes de ele existir (sem olhar o futuro, ADR 0024).
    """
    nomes = {codigo: contrato for codigo, (contrato, _) in CONTRATOS_AGRO.items()}
    tabela = ler_relatorio(conteudo_zip, COLUNAS_DO_DISAGGREGATED, nomes)
    tabela["disponivel_em"] = pd.to_datetime(tabela.pop("divulgado_em")).dt.tz_convert(
        None
    ).dt.normalize() + pd.Timedelta(days=1)
    tabela["relatorio"] = pd.to_datetime(tabela["relatorio"])
    return tabela[list(COLUNAS_AGRO)]


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Só os relatórios que já eram públicos em `dia` (a divulgação conta a partir do dia seguinte)."""
    return tabela[tabela["disponivel_em"] <= pd.Timestamp(dia)].reset_index(drop=True)
