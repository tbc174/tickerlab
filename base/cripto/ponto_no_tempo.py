"""A base de cripto "como era na data" e a prova de que ela se refaz igual (série 1, PR 5;
exigências 3 e 9 do critério de pronto).

Toda tabela da base de cripto tem `divulgado_em` (UTC): o momento a partir do qual aquele número
podia ser conhecido. Montar a base "em D" é ficar só com o que tem `divulgado_em <= D` e, quando a
mesma chave tem várias versões (a Receita refaz meses antigos), com a mais nova até D.

O **hash do conteúdo** prova a reprodutibilidade sem depender de como os arquivos foram gravados
(ler a cadeia em duas vezes ou de uma vez dá arquivos Parquet diferentes, com o mesmo conteúdo):
tira a hora da coleta, ordena pelas chaves e calcula o SHA-256 de um CSV com todas as casas.
"""

import hashlib
from collections.abc import Sequence
from datetime import datetime

import pandas as pd

COLUNAS_QUE_NAO_SAO_CONTEUDO = ("coletado_em",)


def como_era_em(
    tabela: pd.DataFrame, data: datetime, chave: Sequence[str] | None = None
) -> pd.DataFrame:
    """Só as linhas que já existiam na `data`; com `chave`, a versão mais nova de cada chave."""
    antes = tabela[tabela["divulgado_em"] <= pd.Timestamp(data)]
    if chave:
        antes = antes.sort_values("divulgado_em").drop_duplicates(
            list(chave), keep="last"
        )
    return antes.reset_index(drop=True)


def hash_do_conteudo(tabela: pd.DataFrame, ordem: Sequence[str]) -> str:
    """SHA-256 do conteúdo da tabela, sem a hora da coleta e na ordem das chaves."""
    sem_coleta = tabela.drop(
        columns=[c for c in COLUNAS_QUE_NAO_SAO_CONTEUDO if c in tabela]
    )
    canonica = sem_coleta.sort_values(list(ordem)).reset_index(drop=True)
    texto = canonica.to_csv(index=False, float_format="%.17g")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
