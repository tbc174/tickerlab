"""Dívida externa bruta trimestral do Brasil no QEDS do Banco Mundial (A1 da rodada de fontes de 03/11/2026).

A fonte 22 (QEDS/SDDS) da API do Banco Mundial traz a posição bruta de dívida externa do Brasil, todos os
setores, prazos e instrumentos, em US$ (`DT.DOD.DECT.CD.AR.US`), de 1998Q1 em diante. Os 22 primeiros
trimestres vêm sem valor e **ficam nulos**: nunca se preenche. A unidade sai do nome do indicador (os campos
`unit` e `countryiso3code` da API vêm vazios). Não confundir com o `DT.DOD.DECT.CD` anual do WDI (outro
conceito, estoque do IDS).

**Sem olhar o futuro:** a API não tem vintages nem data de divulgação por observação. `disponivel_em` é a
data da coleta em que o valor apareceu (nunca o fim do trimestre) e `acumular` não reescreve a data dos pontos
já conhecidos; um valor revisado entra como versão nova, com a data da coleta que o trouxe.

Licença CC BY 4.0, com atribuição em todo lugar que mostra o dado (`ATRIBUICAO`). Sem Streamlit; pandas só.
"""

import json
import re
from collections.abc import Iterable
from datetime import date

import pandas as pd

FONTE = "worldbank-qeds-brasil"
INDICADOR = "DT.DOD.DECT.CD.AR.US"
PAIS = "BRA"
FONTE_DO_BANCO_MUNDIAL = 22  # QEDS (Quarterly External Debt Statistics, SDDS)
ATRIBUICAO = (
    "Fonte: Banco Mundial, Quarterly External Debt Statistics (QEDS/SDDS), CC BY 4.0, "
    "https://datacatalog.worldbank.org/search/dataset/0037740/quarterly-external-debt-statistics-sdds"
)
COLUNAS = (
    "indicador", "pais", "periodo", "fim_do_trimestre", "valor", "unidade", "disponivel_em",
)  # fmt: skip
CHAVE = ["indicador", "pais", "periodo"]
PERIODO = re.compile(r"^(\d{4})Q([1-4])$")


def unidade_do_nome(nome: str) -> str:
    """A unidade, que é a última parte do nome do indicador ("..., All instruments, USD" → "USD")."""
    unidade = nome.rsplit(", ", 1)[-1].strip()
    if ", " not in nome or not unidade or " " in unidade:
        raise ValueError(f"QEDS: não achei a unidade no nome do indicador {nome!r}")
    return unidade


def _fim_do_trimestre(periodo: str) -> pd.Timestamp:
    ano, trimestre = PERIODO.fullmatch(periodo).groups()  # type: ignore[union-attr]
    return pd.Timestamp(int(ano), int(trimestre) * 3, 1) + pd.offsets.MonthEnd(0)


def _linhas_da_pagina(conteudo: bytes) -> list[dict]:
    try:
        resposta = json.loads(conteudo)
    except ValueError as erro:
        raise ValueError("QEDS: a resposta não é JSON") from erro
    if not (
        isinstance(resposta, list)
        and len(resposta) == 2
        and isinstance(resposta[1], list)
    ):
        raise ValueError(f"QEDS: resposta inesperada: {str(resposta)[:120]}")
    return resposta[1]


def _linha(bruta: dict, coletado_em: date) -> tuple:
    periodo = str(bruta["date"])
    if not PERIODO.fullmatch(periodo):
        raise ValueError(f"QEDS: período fora do formato AAAAQ#: {periodo!r}")
    valor = bruta["value"]
    return (
        bruta["indicator"]["id"],
        bruta["country"]["id"],
        periodo,
        _fim_do_trimestre(periodo),
        float("nan") if valor is None else float(valor),
        unidade_do_nome(bruta["indicator"]["value"]),
        pd.Timestamp(coletado_em),
    )


def ler(paginas: Iterable[bytes], coletado_em: date) -> pd.DataFrame:
    """A série do Brasil, do trimestre mais antigo ao mais novo, coletada em `coletado_em`."""
    linhas = [
        _linha(bruta, coletado_em)
        for pagina in paginas
        for bruta in _linhas_da_pagina(pagina)
        if bruta["indicator"]["id"] == INDICADOR and bruta["country"]["id"] == PAIS
    ]
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS))
    return tabela.sort_values("fim_do_trimestre", kind="stable").reset_index(drop=True)


def acumular(historico: pd.DataFrame, nova: pd.DataFrame) -> pd.DataFrame:
    """O histórico mais o que a coleta nova trouxe de diferente.

    Ponto igual ao último conhecido (nulo contra nulo conta como igual) não entra de novo, então a
    `disponivel_em` dele não muda; ponto novo ou revisado entra com a data da coleta nova.
    """
    if historico.empty:
        return nova.copy()
    ultimas = historico.sort_values("disponivel_em", kind="stable").drop_duplicates(
        CHAVE, keep="last"
    )
    lado_a_lado = nova.merge(
        ultimas[[*CHAVE, "valor"]],
        on=CHAVE,
        how="left",
        suffixes=("", "_antes"),
        indicator=True,
    )
    mesmo_valor = (lado_a_lado["valor"] == lado_a_lado["valor_antes"]) | (
        lado_a_lado["valor"].isna() & lado_a_lado["valor_antes"].isna()
    )
    ja_conhecido = (lado_a_lado["_merge"] == "both") & mesmo_valor
    acumulado = pd.concat(
        [historico, nova[~ja_conhecido.to_numpy()]], ignore_index=True
    )
    return acumulado.sort_values(
        ["fim_do_trimestre", "disponivel_em"], kind="stable"
    ).reset_index(drop=True)


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Para cada trimestre, a versão mais recente que `dia` já conhecia."""
    conhecidas = tabela[tabela["disponivel_em"] <= pd.Timestamp(dia)]
    ordenadas = conhecidas.sort_values("disponivel_em", kind="stable")
    return (
        ordenadas.drop_duplicates(CHAVE, keep="last")
        .sort_values("fim_do_trimestre")
        .reset_index(drop=True)
    )
