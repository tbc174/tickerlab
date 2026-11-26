"""Postos de combustíveis autorizados pela ANP, pelo CNPJ do estabelecimento (linha 1123). Duas tabelas, que se
juntam pelo CNPJ (a coleta é a de `base/arquivo/anp_revendedores.py`):

| Tabela | Fonte | O que traz |
|---|---|---|
| `anp_revendedores` | CSV dos dados abertos (CC BY) | município, bandeira e desde quando, data da autorização |
| `anp_revendedores_produtos` | API da ANP (licença a confirmar, fechada) | por produto: tancagem em m³, bicos e interdição |

Servem para medir a rede de postos de uma empresa fechada e ver a troca de bandeira.

- **Só pessoa jurídica** (ADR 0075): CNPJ com o DV certo; a razão social e o endereço nem chegam ao acervo. A
  raiz de MEI ou de empresário individual é marcada por `trata_como_pessoa`, e a porta a esconde.
- **Sem olhar o futuro:** nenhuma das duas diz quando cada dado foi publicado (as datas são do fato), então a linha
  vale desde o dia em que a vimos. Mudança (bandeira, tancagem, bicos) entra como linha nova naquele dia; o posto
  que sai da lista ganha `consta` falso. O que mudou antes da primeira coleta não aparece.
- A tancagem em unidade que não seja m³ fica vazia e é contada: a API nunca mandou outra (26/11/2026).

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
TABELA_DOS_PRODUTOS = "anp_revendedores_produtos"
FONTE_DO_CADASTRO = arquivista.FONTE_DO_CADASTRO
FONTE_DOS_PRODUTOS = arquivista.FONTE_DOS_PRODUTOS
UNIDADE_DA_TANCAGEM = "m³"
CODIFICACAO_DO_ACERVO = "utf-8"
# a coluna da fonte → a nossa
DATAS_DO_CADASTRO = {
    "DATAPUBLICACAO": "data_da_autorizacao",
    "DATAVINCULACAO": "data_da_vinculacao",
}
TEXTOS_DO_CADASTRO = {"UF": "uf", "MUNICIPIO": "municipio", "BANDEIRA": "bandeira"}
COLUNAS = (
    *leitura.CARIMBO,
    *TEXTOS_DO_CADASTRO.values(),
    *DATAS_DO_CADASTRO.values(),
)
TEXTOS_DOS_PRODUTOS = ("produto", "interdicao")
COLUNAS_DOS_PRODUTOS = (*leitura.CARIMBO, *TEXTOS_DOS_PRODUTOS, "tancagem_m3", "bicos")


def ler_cadastro(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os postos de pessoa jurídica de um CSV do cadastro no acervo e a contagem do que saiu."""
    bruta = leitura.ler_csv(
        conteudo, arquivista.COLUNAS_DO_CADASTRO, CODIFICACAO_DO_ACERVO
    )
    tabela, contagem = comum.so_pessoa_juridica(bruta, "CNPJ")
    return cadastros.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": tabela["cnpj14"],
                **comum.com_cnpj(tabela["cnpj14"]),
                **cadastros.renomeadas(tabela, TEXTOS_DO_CADASTRO),
                **{
                    nosso: leitura.data(tabela[da_fonte])
                    for da_fonte, nosso in DATAS_DO_CADASTRO.items()
                },
            }
        ),
        contagem,
    )


def ler_produtos(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os produtos de cada posto de pessoa jurídica de um CSV da API no acervo e a contagem do que saiu."""
    bruta = leitura.ler_csv(
        conteudo, arquivista.COLUNAS_DOS_PRODUTOS, CODIFICACAO_DO_ACERVO
    )
    tabela, contagem = comum.so_pessoa_juridica(bruta, "cnpj")
    em_m3 = tabela["unidade_da_tancagem"].isin([UNIDADE_DA_TANCAGEM, ""])
    contagem["unidade_desconhecida"] = int((~em_m3).sum())
    return cadastros.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14", "produto"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS_DOS_PRODUTOS},
                "tancagem_m3": comum.numero(tabela["tancagem"].where(em_m3, "")),
                "bicos": leitura.inteiro(tabela["bicos"]),
            }
        ),
        contagem,
        {"tancagem_m3": "float64", "bicos": "Int64"},
    )


CADASTROS = (
    cadastros.cadastro(
        TABELA,
        "cadastro",
        FONTE_DO_CADASTRO,
        ler_cadastro,
        COLUNAS,
        tuple(DATAS_DO_CADASTRO.values()),
    ),
    cadastros.cadastro(
        TABELA_DOS_PRODUTOS,
        "produtos",
        FONTE_DOS_PRODUTOS,
        ler_produtos,
        COLUNAS_DOS_PRODUTOS,
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/<cadastro>.parquet` das duas tabelas, dos retratos guardados."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
