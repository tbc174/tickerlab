"""Bienalidade do arábica: anos "cheio" e "vazio" e a surpresa de quando o ciclo quebra.

O arábica alterna safras altas e baixas (poda, florada e desgaste da planta). Aqui o ano é "cheio" se a
produção do arábica passou da safra anterior e "vazio" se ficou abaixo; usa o levantamento mais novo
já divulgado até a data pedida (a safra em curso entra com o levantamento que existir). A surpresa é o
ciclo quebrado: duas altas ou duas quedas seguidas. O conilon não tem esse ciclo. Funções puras sobre a
tabela `conab_cafe`; sem tela e sem API (licença CC BY-ND 3.0 da CONAB).
"""

from datetime import date
from itertools import pairwise

import pandas as pd

from src.commodities.cafe.pontos import PontoAnual, levantamentos_ate

TIPO = "arabica"
MIL_SACAS = "mil sacas de 60 kg"


def _variacoes(
    tabela: pd.DataFrame, uf: str, ate: date | None
) -> list[tuple[int, int, float]]:
    """(safra, sinal da variação, produção) de cada safra com a anterior ao lado: +1 cheio, -1 vazio."""
    atuais = levantamentos_ate(tabela, TIPO, uf, ate).drop_duplicates(
        "safra", keep="last"
    )
    producao = atuais.set_index("safra")["producao_mil_sacas"].dropna().sort_index()
    saida: list[tuple[int, int, float]] = []
    for anterior, safra in pairwise(producao.index):
        if safra != anterior + 1:
            continue  # buraco na série: não se compara com safra que não é a vizinha
        saida.append(
            (
                int(safra),
                1 if producao[safra] > producao[anterior] else -1,
                float(producao[safra]),
            )
        )
    return saida


def marcar(
    tabela: pd.DataFrame, tipo: str = TIPO, uf: str = "BRASIL", ate: date | None = None
) -> list[PontoAnual]:
    """Uma marca por safra (menos a primeira): rótulo "cheio" ou "vazio" e a produção em mil sacas."""
    if tipo != TIPO:
        raise ValueError(f"só o {TIPO} tem bienalidade, não o {tipo}")
    return [
        PontoAnual(
            safra,
            TIPO,
            uf,
            "ano_cheio_ou_vazio",
            producao,
            MIL_SACAS,
            "cheio" if sinal > 0 else "vazio",
        )
        for safra, sinal, producao in _variacoes(tabela, uf, ate)
    ]


def ciclo_quebrado(
    tabela: pd.DataFrame, tipo: str = TIPO, uf: str = "BRASIL", ate: date | None = None
) -> list[PontoAnual]:
    """Surpresa de bienalidade: 1,0 na safra em que o sinal repetiu o da anterior, 0,0 se alternou."""
    if tipo != TIPO:
        raise ValueError(f"só o {TIPO} tem bienalidade, não o {tipo}")
    variacoes = _variacoes(tabela, uf, ate)
    return [
        PontoAnual(
            safra,
            TIPO,
            uf,
            "ciclo_quebrado",
            float(sinal == anterior),
            "1 = quebrou",
            "quebrou" if sinal == anterior else "manteve",
        )
        for (safra_anterior, anterior, _), (safra, sinal, _) in pairwise(variacoes)
        if safra == safra_anterior + 1
    ]
