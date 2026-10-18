"""Balanço mundial do café do USDA (PSD, Production, Supply and Distribution): produção, consumo,
comércio e estoques por país e ano-safra, em mil sacas de 60 kg (PR 4 da área de commodities).

O arquivo `psd_coffee.csv` (zip de ~440 KB) traz só a versão mais recente de cada número, e em cada
linha diz quando ela foi revisada (`Calendar_Year` e `Month`: o PSD sai em junho e em dezembro, com
revisões pontuais). Cada baixada do arquivista é uma "fotografia"; a tabela junta as fotografias e
guarda `divulgado_em` em cada linha, e `como_estava_em` devolve só o que a data já conhecia (ADR 0024).

O PSD separa a produção em arábica ("Arabica Production") e robusta ("Robusta Production"); o
TickerLab chama a robusta de `conilon` em todo o café, para o mesmo sufixo valer em tabelas e séries.
O resto do balanço (consumo, comércio, estoques) a fonte só traz no total do país.
"""

import io
from datetime import date

import pandas as pd

FONTE = "usda-psd-cafe"
UNIDADE_DA_FONTE = "(1000 60 KG BAGS)"
UNIDADE = "mil sacas de 60 kg"
COLUNAS = (
    "codigo_do_pais", "pais", "ano_safra", "atributo", "tipo", "valor", "unidade", "divulgado_em",
)  # fmt: skip
CHAVE = ["codigo_do_pais", "ano_safra", "atributo", "tipo"]
# atributo da fonte → (atributo da base, tipo); o que não está aqui (importação de grão, solúvel...) sai
ATRIBUTOS = {
    "Production": ("producao", "total"),
    "Arabica Production": ("producao", "arabica"),
    "Robusta Production": ("producao", "conilon"),
    "Domestic Consumption": ("consumo_domestico", "total"),
    "Exports": ("exportacao", "total"),
    "Imports": ("importacao", "total"),
    "Ending Stocks": ("estoque_final", "total"),
    "Beginning Stocks": ("estoque_inicial", "total"),
}  # fmt: skip


def _fim_do_mes(ano: pd.Series, mes: pd.Series) -> pd.Series:
    inicio = pd.to_datetime(
        pd.DataFrame({"year": ano.astype(int), "month": mes.astype(int), "day": 1})
    )
    return inicio + pd.offsets.MonthEnd(0)


def ler(csv: bytes, disponivel_em: date) -> pd.DataFrame:
    """O balanço de um `psd_coffee.csv` baixado em `disponivel_em`.

    `divulgado_em` é o fim do mês da revisão da linha (folga: a USDA publica por volta do dia 10), e
    nunca passa do dia da baixada.
    """
    bruto = pd.read_csv(io.BytesIO(csv), dtype=str, keep_default_na=False)
    bruto = bruto[bruto["Attribute_Description"].isin(ATRIBUTOS)]
    if (bruto["Unit_Description"] != UNIDADE_DA_FONTE).any():
        raise ValueError(
            f"PSD: unidade diferente de {UNIDADE_DA_FONTE}; conferir antes de gravar"
        )
    traduzido = bruto["Attribute_Description"].map(ATRIBUTOS)
    divulgado = _fim_do_mes(bruto["Calendar_Year"], bruto["Month"])
    tabela = pd.DataFrame(
        {
            "codigo_do_pais": bruto["Country_Code"].str.strip(),
            "pais": bruto["Country_Name"].str.strip(),
            "ano_safra": bruto["Market_Year"].astype(int),
            "atributo": traduzido.str[0],
            "tipo": traduzido.str[1],
            "valor": pd.to_numeric(bruto["Value"], errors="coerce"),
            "unidade": UNIDADE,
            "divulgado_em": divulgado.clip(upper=pd.Timestamp(disponivel_em)),
        }
    )
    return tabela.dropna(subset=["valor"]).reset_index(drop=True)[list(COLUNAS)]


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Para cada país, safra, atributo e tipo, a versão mais recente que `dia` já conhecia."""
    conhecidas = tabela[tabela["divulgado_em"] <= pd.Timestamp(dia)]
    ordenadas = conhecidas.sort_values("divulgado_em", kind="stable")
    return ordenadas.drop_duplicates(CHAVE, keep="last").reset_index(drop=True)
