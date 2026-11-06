"""O que os leitores das fontes setoriais repetem."""

import numpy as np
import pandas as pd


def sem_espacos(coluna: pd.Series, *, vazio_vira_none: bool = False) -> pd.Series:
    """O texto sem espaços nas pontas, limpo pelos valores distintos: um ano tem milhões de linhas e
    poucos milhares de valores, e um texto novo por célula estourou 4 GB no ONS de 2023 (#306).

    `vazio_vira_none`: o texto vazio vira None (o ONS guarda o vazio como veio).
    """
    codigos, distintos = pd.factorize(coluna)
    limpos = pd.Series(distintos).astype("string").str.strip().astype(object)
    if vazio_vira_none:
        limpos = limpos.mask(limpos.eq(""), None)
    com_o_vazio = np.append(
        limpos.to_numpy(), None
    )  # o código -1 (vazio) pega o último: None
    return pd.Series(com_o_vazio[codigos], index=coluna.index, dtype=object)
