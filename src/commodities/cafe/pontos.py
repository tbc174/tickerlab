"""O ponto de uma série anual do café: uma dataclass simples, que vira JSON sem adaptação.

Os derivados da CONAB (`termometro`, `bienalidade`) devolvem `list[PontoDaSafra]`. Pela ADR 0102 eles
podem ir para tela, API e PDF com a fonte e a data citadas: cada ponto carrega `divulgado_em`, o dia do
último levantamento da CONAB que ele usa, e `citacao(ponto)` escreve a frase (licença CC BY-ND 3.0
registrada na marca da fonte, `src/banco/coletas.py`).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

FONTE_DA_CONAB = "CONAB, Acompanhamento da Safra Brasileira de Café"
LICENCA_DA_CONAB = "CC BY-ND 3.0"


@dataclass(frozen=True)
class PontoDaSafra:
    safra: int  # ano em que a safra começa
    tipo: str  # arabica, conilon ou total
    uf: str
    serie: str  # o que o valor mede
    valor: float
    unidade: str
    rotulo: str | None = None  # texto do ponto, quando há (ex.: "cheio")
    levantamento: int | None = None  # levantamento de onde o valor saiu, quando é um só
    # dia (ISO) em que a CONAB divulgou o último levantamento que o valor usa: a data a citar (ADR 0102)
    divulgado_em: str | None = None


def dia_iso(valor: object) -> str | None:
    """`divulgado_em` da tabela (Timestamp) como "AAAA-MM-DD"; vazio vira None."""
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]


def citacao(ponto: PontoDaSafra) -> str:
    """A frase de fonte do ponto, para a tela, a API e o PDF: a CONAB, até que data e a licença."""
    ate = ""
    if ponto.divulgado_em:
        dia = date.fromisoformat(ponto.divulgado_em)
        ate = f", levantamentos divulgados até {dia:%d/%m/%Y}"
    return f"{FONTE_DA_CONAB}{ate} ({LICENCA_DA_CONAB})"


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
