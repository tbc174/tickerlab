"""Meses revisados (série 4, PR 5): ANS, Anatel e ANEEL republicam o arquivo inteiro a cada mês e
podem mudar um mês passado. Cada baixada do arquivista é uma "coleta"; a tabela guarda uma linha por
**valor diferente** de cada chave, como a base de demonstrações (`base/ponto_no_tempo.py`):

- o primeiro valor visto de uma chave vale desde a regra do prazo da fonte (`disponivel_em` do leitor);
- um valor diferente numa coleta seguinte (a revisão) vale só desde o dia da coleta que o trouxe
  (`visto_em`), ou desde o prazo, se for depois: a revisão nunca volta para antes de ser vista;
- o mesmo valor visto de novo não vira linha nova; linha que some numa coleta seguinte fica como estava.

Limite conhecido: o que mudou **antes da primeira coleta** não aparece (o arquivista começou em
10/2026); o valor do passado é o da primeira coleta, com a data do prazo. `como_era_em` devolve, numa
data, o valor que era público em cada chave.
"""

from collections.abc import Sequence

import pandas as pd

VISTO_EM = "visto_em"


def juntar_coletas(
    coletas: Sequence[tuple[pd.Timestamp, pd.DataFrame]],
    chave: list[str],
    carimbos: Sequence[str] = (),
) -> pd.DataFrame:
    """As coletas (dia da baixada, tabela lida com `disponivel_em`) numa tabela com as revisões.

    `chave` identifica uma linha dentro de uma coleta; `carimbos` são colunas que mudam a cada
    publicação sem mudar o número (a data de geração do SAMP) e não contam como revisão.
    """
    if not coletas:
        raise ValueError("nenhuma coleta para juntar")
    partes = [tabela.assign(**{VISTO_EM: pd.Timestamp(dia)}) for dia, tabela in coletas]
    todas = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
    valores = [
        c for c in todas.columns if c not in ("disponivel_em", VISTO_EM, *carimbos)
    ]
    unicas = todas.sort_values(VISTO_EM, kind="stable").drop_duplicates(
        valores, keep="first"
    )
    revisao = unicas.duplicated(chave, keep="first")
    unicas.loc[revisao, "disponivel_em"] = unicas.loc[
        revisao, ["disponivel_em", VISTO_EM]
    ].max(axis=1)
    return unicas.reset_index(drop=True)


def como_era_em(tabela: pd.DataFrame, data: object, chave: list[str]) -> pd.DataFrame:
    """Um valor por chave: o mais novo já público no dia `data` (a revisão vista depois não entra)."""
    dia = pd.Timestamp(data)  # type: ignore[arg-type]
    publico = tabela[tabela["disponivel_em"] <= dia]
    ordem = publico.sort_values(["disponivel_em", VISTO_EM], kind="stable")
    return ordem.drop_duplicates(chave, keep="last").reset_index(drop=True)
