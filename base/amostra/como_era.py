"""A regra "como era na data" da amostra integrada, igual para todos os blocos (ADR 0027, exigência 3).

Cada tabela de entrada diz, pelo contrato, desde quando cada linha era pública (`publico_em`) e, quando
existe, até quando valeu (`termina_em`: o cancelamento do registro, o fim da validade de um ticker).
Numa data, um bloco só pode usar as linhas com `publico_em` <= data, e o `termina_em` que ainda estava no
futuro é desconhecido.

`cortar` faz exatamente isso com a base inteira; o teste de cada bloco monta o painel com a base cortada
numa data e confere que a linha daquela data é a mesma do painel montado com a base inteira. Se for
diferente, o bloco usou algo que só ficou público depois.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

INICIO = pd.Timestamp(
    "2010-01-31"
)  # o primeiro mês do painel (DFP e ITR abertos desde 2010/2011)
DATA = "datetime64[ns]"


@dataclass(frozen=True)
class Entrada:
    """Uma tabela de entrada de um bloco: a coluna de quando a linha ficou pública e, se houver, a de
    quando deixou de valer."""

    publico_em: str
    termina_em: str | None = None


def fins_de_mes(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DatetimeIndex:
    """O último dia de cada mês de `inicio` a `fim` (inclusive o mês de `fim`, se `fim` é fim de mês)."""
    return pd.date_range(inicio, fim, freq="ME")


def cortar(
    entradas: Mapping[str, pd.DataFrame],
    definicoes: Mapping[str, Entrada],
    data: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """A base como era em `data`: sem as linhas que ainda não eram públicas e sem os fins de validade
    que ainda estavam no futuro."""
    cortadas = {}
    for nome, tabela in entradas.items():
        definicao = definicoes[nome]
        publica = pd.to_datetime(tabela[definicao.publico_em]) <= data
        cortada = tabela[publica].copy()
        if definicao.termina_em is not None:
            termina = pd.to_datetime(cortada[definicao.termina_em])
            cortada[definicao.termina_em] = termina.where(termina <= data)
        cortadas[nome] = cortada.reset_index(drop=True)
    return cortadas


def ultimo_publico(
    grade: pd.DataFrame,
    tabela: pd.DataFrame,
    *,
    publico_em: str,
    colunas: list[str],
    prefixo: str,
    por: str = "cnpj",
) -> pd.DataFrame:
    """A grade (`por`, `data`) com, em cada linha, as `colunas` da linha mais nova da tabela já
    pública na data, e `<prefixo>_publico_em` (quando ela ficou pública). Sem valor público: vazio.

    No empate de `publico_em`, vale a última linha da tabela na ordem dada (quem chama ordena).
    """
    coluna_da_data = f"{prefixo}_publico_em"
    direita = tabela[[por, publico_em, *colunas]].rename(
        columns={publico_em: coluna_da_data}
    )
    direita = direita.dropna(subset=[coluna_da_data])
    direita[coluna_da_data] = pd.to_datetime(direita[coluna_da_data]).astype(DATA)
    direita = direita.sort_values(coluna_da_data, kind="stable")
    esquerda = grade.assign(data=pd.to_datetime(grade["data"]).astype(DATA))
    juntas = pd.merge_asof(
        esquerda.sort_values("data", kind="stable"),
        direita,
        left_on="data",
        right_on=coluna_da_data,
        by=por,
        direction="backward",
    )
    return juntas.sort_values([por, "data"]).reset_index(drop=True)
