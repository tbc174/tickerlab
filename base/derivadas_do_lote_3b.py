"""Tabelas por CNPJ do lote 3 que vêm de arquivo de documento misto (CPF e CNPJ no mesmo campo), linha 904:
os estabelecimentos registrados no SIF e as transações tributárias da Receita (acordos individuais e adesões).

Mesmo molde do PR do lote 3 (`base/derivadas_do_lote_3.py`): **só pessoa jurídica**. Os leitores
(`base/sigsif.py`, `base/receita_transacoes.py`) já tiram o CPF; aqui a raiz de MEI, empresário individual,
natureza do grupo 4 ou que a Receita guardada não tem sai da tabela inteira, e **nenhum nome é gravado**: nem a
razão social do SIF, nem o `contribuinte` dos acordos individuais (que num MEI seria o nome de uma pessoa).

- **`sigsif_estabelecimentos`**: quem tem registro no SIF (Serviço de Inspeção Federal), onde e em que categoria.
- **`receita_transacoes_individual`**: acordos de transação tributária deferidos (poucas dezenas de CNPJs).
- **`receita_transacoes_adesao`**: adesões às modalidades de transação (PRLF, editais, Litígio Zero).

**Sem olhar o futuro:** nenhuma fonte diz quando cada linha foi entregue. `disponivel_em` é a data de
modificação do arquivo na fonte (SIGSIF: o `Last-Modified`; transações: o "Atualizado em" da página).

Sem Streamlit; pandas só.
"""

import pandas as pd

from base.derivadas_do_lote_3 import (
    COLUNAS_DO_CNPJ,
    DescobrirPessoas,
    separar_pessoa_juridica,
)

TABELA_ESTABELECIMENTOS = "sigsif_estabelecimentos"
TABELA_ACORDOS = "receita_transacoes_individual"
TABELA_ADESOES = "receita_transacoes_adesao"

COLUNAS_DOS_ESTABELECIMENTOS = (
    *COLUNAS_DO_CNPJ, "nr_sif", "situacao", "municipio", "uf", "area_categoria", "categoria_classe",
)  # fmt: skip
CHAVE_DOS_ESTABELECIMENTOS = (
    "cnpj", "nr_sif", "area_categoria", "categoria_classe", "municipio",
)  # fmt: skip

COLUNAS_DOS_ACORDOS = (
    *COLUNAS_DO_CNPJ, "processo", "data_acordo", "divida_transacionada", "reducao",
    "divida_com_reducao", "creditos_pf_bcn", "saldo_devedor",
)  # fmt: skip
CHAVE_DOS_ACORDOS = ("cnpj", "processo")

COLUNAS_DAS_ADESOES = (
    *COLUNAS_DO_CNPJ, "modalidade", "data_requerimento", "divida_sem_reducao", "reducao",
    "credito_pf_proprio", "credito_pf_terceiros", "credito_bcn_proprio", "credito_bcn_terceiros",
    "parcelas", "hash_linha",
)  # fmt: skip
CHAVE_DAS_ADESOES = ("hash_linha",)

_DE_PESSOA = ["trata_como_pessoa", "disponivel_em"]


def estabelecimentos_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os registrados lidos por `sigsif.ler_estabelecimentos`, só de pessoa jurídica e sem a razão social.
    O mesmo estabelecimento listado duas vezes com os mesmos campos fica uma vez (`repetidas` na contagem)."""
    pj, contagem = separar_pessoa_juridica(lido, descobrir)
    pronta = pj[[*COLUNAS_DOS_ESTABELECIMENTOS, *_DE_PESSOA]]
    unica = pronta.drop_duplicates(list(CHAVE_DOS_ESTABELECIMENTOS))
    contagem["repetidas"] = len(pronta) - len(unica)
    contagem["linhas_na_tabela"] = len(unica)
    pronta_final = unica.reset_index(drop=True)
    pronta_final.attrs = {}  # os avisos da leitura (conjuntos) não vão para o Parquet
    return pronta_final, contagem


def acordos_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os acordos lidos por `receita_transacoes.ler_individual`, só de pessoa jurídica e sem o contribuinte."""
    pj, contagem = separar_pessoa_juridica(lido, descobrir)
    return pj[[*COLUNAS_DOS_ACORDOS, *_DE_PESSOA]].reset_index(drop=True), contagem


def adesoes_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As adesões lidas por `receita_transacoes.ler_adesao`, só de pessoa jurídica."""
    pj, contagem = separar_pessoa_juridica(lido, descobrir)
    return pj[[*COLUNAS_DAS_ADESOES, *_DE_PESSOA]].reset_index(drop=True), contagem
