"""Tabela `anp_revendedores`: os postos de combustíveis autorizados pela ANP, por CNPJ de estabelecimento (linha 1123).

Uma linha por posto e produto: a bandeira (distribuidora, ou bandeira branca) e desde quando, a data da
autorização, o município e, por produto, a capacidade de tancagem em m³ e o número de bicos. Serve para medir a
rede de postos de uma empresa fechada e ver a troca de bandeira. A coleta é a de `base/arquivo/anp_revendedores.py`.

- **Só pessoa jurídica** (ADR 0075): CNPJ com o DV certo; a razão social e o endereço nem chegam ao acervo. A
  raiz de MEI ou de empresário individual é marcada por `trata_como_pessoa`, e a porta a esconde.
- **Sem olhar o futuro:** a API não diz quando cada dado foi publicado (as datas dela são do fato), então a linha
  vale desde o dia em que a vimos. Mudança (bandeira, tancagem, bicos) entra como linha nova naquele dia; o posto
  que sai da lista ganha `consta` falso. O que mudou antes da primeira coleta não aparece.
- A tancagem em unidade que não seja m³ fica vazia e é contada: a fonte nunca mandou outra (26/11/2026).

Sem Streamlit; pandas só.
"""

from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import bcb_cadastros as cadastros
from base import cadastros_conferidos as leitura
from base import cadastros_em_retrato
from base import retratos as motor
from base.arquivo import anp_revendedores as arquivista

TABELA = "anp_revendedores"
NOME = "revendedores"
FONTE = arquivista.FONTE
UNIDADE_DA_TANCAGEM = "m³"
TEXTOS = ("codigo_simp", "autorizacao", "uf", "municipio", "bandeira", "produto")
DATAS = ("data_da_autorizacao", "data_da_vinculacao")
COLUNAS = (*leitura.CARIMBO, *TEXTOS, *DATAS, "tancagem_m3", "bicos")


def ler(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os postos de pessoa jurídica de um CSV do acervo e a contagem do que saiu."""
    bruta = leitura.ler_csv(conteudo, arquivista.COLUNAS, "utf-8")
    tabela, contagem = comum.so_pessoa_juridica(bruta, "cnpj")
    em_m3 = tabela["unidade_da_tancagem"].isin([UNIDADE_DA_TANCAGEM, ""])
    contagem["unidade_desconhecida"] = int((~em_m3).sum())
    return cadastros.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14", "produto"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
                **{c: leitura.data(tabela[c]) for c in DATAS},
                "tancagem_m3": comum.numero(tabela["tancagem"].where(em_m3, "")),
                "bicos": leitura.inteiro(tabela["bicos"]),
            }
        ),
        contagem,
        {"tancagem_m3": "float64", "bicos": "Int64"},
    )


CADASTRO = cadastros.cadastro(TABELA, NOME, FONTE, ler, COLUNAS, DATAS)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/anp_revendedores/revendedores.parquet` dos retratos guardados (`cadastros_em_retrato`)."""
    return cadastros_em_retrato.montar(
        (CADASTRO,), conexao, pasta, agora, pessoas, refazer
    )
