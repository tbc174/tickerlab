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
    direita[por] = direita[por].astype(
        object
    )  # texto do pandas 3 e "object" não se juntam
    esquerda = grade.assign(data=pd.to_datetime(grade["data"]).astype(DATA))
    esquerda[por] = esquerda[por].astype(object)
    juntas = pd.merge_asof(
        esquerda.sort_values("data", kind="stable"),
        direita,
        left_on="data",
        right_on=coluna_da_data,
        by=por,
        direction="backward",
    )
    return juntas.sort_values([por, "data"]).reset_index(drop=True)


def na_janela(
    fatos: pd.DataFrame,
    *,
    data_do_fato: str,
    publico_em: str,
    dias: int,
    ultimo_mes: pd.Timestamp,
) -> pd.DataFrame:
    """Cada fato repetido em cada fim de mês em que ele conta numa janela de `dias`: o fim de mês `m`
    conta o fato se ele já era público (`publico_em` <= m) e aconteceu nos `dias` antes de `m`
    (`m - dias` < `data_do_fato` <= m). Devolve as colunas dos fatos e `data` (o fim de mês).

    Cada fato vira 3 ou 4 linhas numa janela de 90 dias, em vez de juntar todos os fatos a todos os
    meses de cada companhia.
    """
    tabela = fatos.dropna(subset=[data_do_fato, publico_em]).copy()
    fato = pd.to_datetime(tabela[data_do_fato]).astype(DATA)
    publico = pd.to_datetime(tabela[publico_em]).astype(DATA)
    primeiro = (pd.concat([fato, publico], axis=1).max(axis=1)) + pd.offsets.MonthEnd(0)
    limite = fato + pd.Timedelta(days=dias)  # o fim de mês tem de ser antes disto
    meses = (
        (limite.dt.year - primeiro.dt.year) * 12
        + (limite.dt.month - primeiro.dt.month)
        + 1
    ).clip(lower=0)
    tabela = tabela.assign(_primeiro=primeiro, _limite=limite).loc[
        meses.index.repeat(meses)
    ]
    deslocamento = tabela.groupby(level=0).cumcount()
    tabela["data"] = (
        (tabela["_primeiro"].dt.to_period("M") + deslocamento.to_numpy())
        .dt.to_timestamp(how="end")
        .dt.normalize()
        .astype(DATA)
    )
    vale = (tabela["data"] < tabela["_limite"]) & (tabela["data"] <= ultimo_mes)
    return tabela[vale].drop(columns=["_primeiro", "_limite"]).reset_index(drop=True)
