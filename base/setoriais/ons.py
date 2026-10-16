"""Geração por usina do ONS (série 4, PR 4): MWmed por hora e usina, no formato da fonte.

A chave da usina é o `id_ons` (um nome só por código): o CEG da ANEEL falta em 41% da geração de
09/2026 (conjuntos eólicos e solares, pequenas centrais agregadas, com "-") e o mesmo CEG pode ter
dois `id_ons` (Itaipu 50 e 60 Hz). Os arquivos antigos trazem a geração como texto ("0E-8").

Sem ligação à empresa neste PR: o dono da usina só existe no cadastro de capacidade do ONS, que é o de
hoje, e aplicá-lo à geração do passado seria olhar o futuro (usinas mudam de dono).
"""

import io

import numpy as np
import pandas as pd

from base.setoriais import prazos

FONTE = "ons-geracao-usina"
SEM_CODIGO = ("-", "")
COLUNAS = (
    "instante", "id_subsistema", "subsistema", "uf", "modalidade_de_operacao", "tipo_de_usina",
    "combustivel", "usina", "id_ons", "ceg", "geracao_mwmed", "disponivel_em",
)  # fmt: skip
NOMES = {
    "din_instante": "instante", "id_subsistema": "id_subsistema", "nom_subsistema": "subsistema",
    "id_estado": "uf", "cod_modalidadeoperacao": "modalidade_de_operacao",
    "nom_tipousina": "tipo_de_usina", "nom_tipocombustivel": "combustivel", "nom_usina": "usina",
    "id_ons": "id_ons", "ceg": "ceg", "val_geracao": "geracao_mwmed",
}  # fmt: skip
TEXTOS = (
    "id_subsistema", "subsistema", "uf", "modalidade_de_operacao", "tipo_de_usina", "combustivel",
    "usina", "id_ons", "ceg",
)  # fmt: skip


def _sem_espacos(coluna: pd.Series) -> pd.Series:
    """O texto sem espaços nas pontas, limpo pelos valores distintos: um ano tem milhões de linhas e
    poucos milhares de valores, e um texto novo por célula estourou 4 GB no ONS de 2023."""
    codigos, distintos = pd.factorize(coluna)
    limpos = pd.Series(distintos).astype("string").str.strip().astype(object).to_numpy()
    com_o_vazio = np.append(limpos, None)  # o código -1 (vazio) pega o último: None
    return pd.Series(com_o_vazio[codigos], index=coluna.index, dtype=object)


def ler(conteudo_do_parquet: bytes) -> pd.DataFrame:
    """Um arquivo de geração do ONS (anual ou mensal), com `disponivel_em`."""
    tabela = pd.read_parquet(io.BytesIO(conteudo_do_parquet)).rename(columns=NOMES)
    tabela["instante"] = pd.to_datetime(tabela["instante"])
    geracao = tabela["geracao_mwmed"]
    if not pd.api.types.is_numeric_dtype(geracao):
        geracao = geracao.astype(str)
    tabela["geracao_mwmed"] = pd.to_numeric(geracao, errors="coerce").astype(float)
    for coluna in TEXTOS:
        tabela[coluna] = _sem_espacos(tabela[coluna])
    sem_ceg = tabela["ceg"].isna() | tabela["ceg"].isin(SEM_CODIGO)
    tabela["ceg"] = tabela["ceg"].mask(sem_ceg, None)
    tabela["disponivel_em"] = prazos.disponivel_ons(tabela["instante"])
    return tabela.reindex(columns=list(COLUNAS))
