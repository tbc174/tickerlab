"""Prêmios e sinistros de seguros por seguradora, ramo e mês (SES da SUSEP; série 4, PR 5b), no formato
da fonte (as colunas com o nome da SUSEP, em minúsculas).

O SES inteiro é um ZIP de ~580 MB regerado todo dia; o arquivista guarda só os CSVs de seguros e os
cadastros (seguradoras, ramos e grupos de ramos), nunca os que têm pessoas (administradores, contatos,
acionistas). `Ses_seguros.csv` tem 1,8 milhão de linhas desde 01/1995 e nenhuma chave repetida (medido
em 16/10/2026); os meses passados podem mudar (`base/setoriais/revisoes.py`).

A chave da seguradora é o código da SUSEP (`coenti`). O cadastro da SUSEP não traz CNPJ e a B13 ainda
não liga esse código a uma empresa: todos vão para os buracos, a lista de trabalho da conferência.
"""

import io

import pandas as pd

from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE = "susep-ses"
ARQUIVO = "Ses_seguros.csv"
CODIFICACAO = "latin-1"
TEXTOS = ("coenti", "cogrupo", "coramo")
NUMEROS = (
    "premio_direto", "premio_de_seguros", "premio_retido", "premio_ganho", "sinistro_direto",
    "sinistro_retido", "desp_com", "premio_emitido2", "premio_emitido_cap", "despesa_resseguros",
    "sinistro_ocorrido", "receita_resseguro", "sinistros_ocorridos_cap",
    "recuperacao_sinistros_ocorridos_cap", "rvne", "conveniodpvat", "consorciosefundos",
)  # fmt: skip
COLUNAS = ("competencia", *TEXTOS, *NUMEROS, "disponivel_em")
CHAVE = ["competencia", *TEXTOS]


def _numero(coluna: pd.Series) -> pd.Series:
    """O número com vírgula decimal ("350407,58"); o vazio fica vazio."""
    return pd.to_numeric(
        coluna.str.replace(",", ".", regex=False), errors="coerce"
    ).astype(float)


def ler(conteudo: bytes) -> pd.DataFrame:
    """`Ses_seguros.csv` inteiro, com a competência (último dia do mês) e `disponivel_em`."""
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding=CODIFICACAO,
        keep_default_na=False,
    )
    bruto.columns = [c.strip().lower() for c in bruto.columns]
    tabela = pd.DataFrame(
        {c: sem_espacos(bruto[c], vazio_vira_none=True) for c in TEXTOS}
    )
    for coluna in NUMEROS:
        tabela[coluna] = _numero(bruto[coluna])
    tabela["competencia"] = prazos.fim_do_mes(
        bruto["damesano"].str[:4], bruto["damesano"].str[4:6]
    )
    tabela["disponivel_em"] = prazos.disponivel_mensal(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
