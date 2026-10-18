"""O ponto de uma série anual do café: uma dataclass simples, que vira JSON sem adaptação.

Os derivados da CONAB (`termometro`, `bienalidade`) devolvem `list[PontoAnual]`. Por causa da licença
CC BY-ND 3.0 da CONAB, nenhum desses números sai por tela, API ou exportação até a resposta dela.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class PontoAnual:
    safra: int  # ano em que a safra começa
    tipo: str  # arabica, conilon ou total
    uf: str
    serie: str  # o que o valor mede
    valor: float
    unidade: str
    rotulo: str | None = None  # texto do ponto, quando há (ex.: "cheio")
    levantamento: int | None = None  # levantamento de onde o valor saiu, quando é um só


def levantamentos_ate(
    tabela: pd.DataFrame, tipo: str, uf: str, ate: date | None
) -> pd.DataFrame:
    """Um registro por (safra, levantamento): a revisão mais nova já divulgada até `ate` (inclusive).

    Sem `ate`, vale tudo o que a tabela tem. É o corte que impede olhar o futuro: o que foi
    divulgado depois de `ate` não existe para quem pergunta com aquela data.
    """
    linhas = tabela[(tabela["tipo"] == tipo) & (tabela["uf"] == uf)]
    if ate is not None:
        linhas = linhas[linhas["divulgado_em"] <= pd.Timestamp(ate)]
    ordem = linhas.sort_values(["divulgado_em", "levantamento"])
    ultimas = ordem.drop_duplicates(["safra", "levantamento"], keep="last")
    return ultimas.sort_values(["safra", "levantamento"]).reset_index(drop=True)
