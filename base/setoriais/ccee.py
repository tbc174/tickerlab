"""PLD da CCEE (série T, PR T6): preço da energia no mercado de curto prazo, em R$/MWh, por submercado.

Seis desenhos de CSV (aspas e CRLF até 2024, sem aspas e LF depois; latin-1), três granularidades:

- **hora** (desde 01/2021): `PERIODO_COMERCIALIZACAO` é a hora do mês (1 a 744), `DIA` e `HORA` dizem qual;
- **dia** (desde 01/2021) e **mês** (desde 01/2001): a média publicada pela CCEE, não recalculada aqui;
- o arquivo "horário" de 06/2001 a 12/2020 **não é horário**: é um preço por semana e patamar de carga,
  três linhas por semana e submercado, sem rótulo do patamar. O desenho fica como a fonte (granularidade
  `semana_por_patamar`) e a posição entre as linhas repetidas vai em `ordem`: o rótulo não se inventa.
"""

import io

import pandas as pd

from base.setoriais import prazos

FONTE = "ccee-pld"
GRANULARIDADES = ("hora", "dia", "mes", "semana_por_patamar")
COLUNAS = (
    "granularidade", "submercado", "referencia", "competencia", "ordem",
    "periodo_de_comercializacao", "pld", "disponivel_em",
)  # fmt: skip
CHAVE = ("granularidade", "submercado", "referencia", "ordem")
PRIMEIRO_MES_HORARIO = "202101"  # a CCEE passou ao preço horário em 01/01/2021


def _csv(conteudo: bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
    )


def _competencia(mes_de_referencia: pd.Series) -> pd.Series:
    return pd.to_datetime(mes_de_referencia, format="%Y%m") + pd.offsets.MonthEnd(0)


def _horario(tabela: pd.DataFrame) -> pd.DataFrame:
    competencia = _competencia(tabela["MES_REFERENCIA"])
    dia = tabela["DIA"].astype(int)
    antigo = (tabela["MES_REFERENCIA"] < PRIMEIRO_MES_HORARIO).all()
    inicio = competencia.dt.to_period("M").dt.to_timestamp()
    referencia = inicio + pd.to_timedelta(dia - 1, unit="D")
    if not antigo:
        referencia = referencia + pd.to_timedelta(tabela["HORA"].astype(int), unit="h")
    return pd.DataFrame(
        {
            "granularidade": "semana_por_patamar" if antigo else "hora",
            "submercado": tabela["SUBMERCADO"],
            "referencia": referencia,
            "competencia": competencia,
            "periodo_de_comercializacao": tabela["PERIODO_COMERCIALIZACAO"].astype(int),
            "pld": tabela["PLD_HORA"].astype(float),
        }
    )


def _diario(tabela: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "granularidade": "dia",
            "submercado": tabela["SUBMERCADO"],
            "referencia": pd.to_datetime(tabela["DIA"], format="%d/%m/%Y"),
            "competencia": _competencia(tabela["MES_REFERENCIA"]),
            "periodo_de_comercializacao": pd.NA,
            "pld": tabela["PLD_MEDIA_DIA"].astype(float),
        }
    )


def _mensal(tabela: pd.DataFrame) -> pd.DataFrame:
    competencia = _competencia(tabela["MES_REFERENCIA"])
    return pd.DataFrame(
        {
            "granularidade": "mes",
            "submercado": tabela["SUBMERCADO"],
            "referencia": competencia.dt.to_period("M").dt.to_timestamp(),
            "competencia": competencia,
            "periodo_de_comercializacao": pd.NA,
            "pld": tabela["PLD_MEDIA_MES"].astype(float),
        }
    )


def ler(conteudo: bytes) -> pd.DataFrame:
    """Um CSV de PLD (qualquer um dos seis desenhos), com a `ordem` das linhas repetidas e
    `disponivel_em`."""
    bruta = _csv(conteudo)
    if "PLD_HORA" in bruta:
        tabela = _horario(bruta)
    elif "PLD_MEDIA_DIA" in bruta:
        tabela = _diario(bruta)
    elif "PLD_MEDIA_MES" in bruta:
        tabela = _mensal(bruta)
    else:
        raise ValueError(f"desenho de PLD desconhecido: colunas {list(bruta.columns)}")
    tabela["submercado"] = tabela["submercado"].str.strip()
    tabela["periodo_de_comercializacao"] = tabela["periodo_de_comercializacao"].astype(
        "Int64"
    )
    tabela["ordem"] = (
        tabela.groupby(["granularidade", "submercado", "referencia"]).cumcount() + 1
    )
    if tabela.empty:
        return tabela.assign(ordem=1, disponivel_em=pd.NaT).reindex(
            columns=list(COLUNAS)
        )
    granularidade = str(tabela["granularidade"].iloc[0])
    tabela["disponivel_em"] = prazos.disponivel_pld(
        tabela["referencia"], tabela["competencia"], granularidade
    )
    return tabela.reindex(columns=list(COLUNAS))
