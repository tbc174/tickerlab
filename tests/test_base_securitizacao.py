"""Informes mensais de CRI, CRA e outros títulos de securitização (OTS) da CVM, sem dado pessoal.

Amostras reais recortadas (`tests/arquivos/cvm/securitizacao/`: 4 certificados por arquivo, todos os
quadros), geradas uma vez dos arquivos de 18/10/2026: CPFs e nomes trocados por fictícios, textos
livres por um texto neutro. Ficam os casos que o leitor precisa tratar: a linha quebrada do CRA
(um `;` dentro do campo), a chave repetida do OTS, o quadro `responsavel` do CRI de 2019 (nome e
cargo de pessoa) e valores que não são CNPJ no campo `CNPJ` dos cedentes e devedores.
"""

import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base import securitizacao

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "securitizacao"
ARQUIVOS = {
    "inf_mensal_cri_2019.zip": "cri",
    "inf_mensal_cri_2026.zip": "cri",
    "inf_mensal_cra_2026.zip": "cra",
    "inf_mensal_ots_2026.zip": "ots",
}
CPF_FICTICIO = "52998224725"  # dígitos verificadores certos, de ninguém
QUADROS_DA_CVM_175 = {
    "geral",
    "ativo_passivo",
    "classe",
    "direitos_creditorios",
    "cedente_devedor",
    "fluxo_caixa",
    "desembolso",
    "derivativos",
}
QUADROS_DO_CRI = {
    "geral",
    "ativo_passivo",
    "carteira",
    "carteira_modificacao",
    "classe",
    "creditos",
    "derivativos",
    "desembolso",
    "fluxo_caixa",
}


def _bytes(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _ler(nome: str) -> securitizacao.Leitura:
    return securitizacao.ler_informe(_bytes(nome), ARQUIVOS[nome])


def _linhas_distintas(nome: str, quadro: str) -> int:
    """As linhas diferentes do quadro no arquivo bruto com o número certo de campos."""
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        (interno,) = [
            n for n in arquivo.namelist() if re.search(rf"_{quadro}_\d{{4}}", n)
        ]
        linhas = arquivo.read(interno).decode("latin-1").splitlines()
    campos = linhas[0].count(";")
    return len({linha for linha in linhas[1:] if linha.count(";") == campos})


@pytest.mark.parametrize(
    ("nome", "esperados"),
    [
        ("inf_mensal_cri_2019.zip", QUADROS_DO_CRI),
        # em 2026 o CRI ganhou cedentes e devedores e perdeu as modificações da carteira
        (
            "inf_mensal_cri_2026.zip",
            QUADROS_DO_CRI - {"carteira_modificacao"} | {"cedente_devedor"},
        ),
        ("inf_mensal_cra_2026.zip", QUADROS_DA_CVM_175),
        ("inf_mensal_ots_2026.zip", QUADROS_DA_CVM_175),
    ],
)
def test_quadros_por_ano(nome, esperados):
    assert esperados <= securitizacao.quadros_do_arquivo(_bytes(nome), ARQUIVOS[nome])
    assert esperados <= set(_ler(nome).tabelas)


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_chave_e_competencia(nome):
    tabelas = _ler(nome).tabelas
    assert tabelas
    for quadro, tabela in tabelas.items():
        assert list(tabela.columns[:3]) == list(securitizacao.CHAVE), quadro
        assert (tabela["competencia"].dt.day == 1).all(), quadro
        assert (
            tabela["cnpj_securitizadora"]
            .str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
            .all()
        ), quadro
        assert tabela["codigo_certificado"].notna().all(), quadro
        # linha repetida inteira (o OTS tem) entra uma vez só
        assert len(tabela) == _linhas_distintas(nome, quadro), quadro


def test_competencia_do_ots_e_o_primeiro_dia_do_mes():
    # o OTS informa o último dia do mês (2026-03-31); CRI e CRA, o primeiro
    geral = _ler("inf_mensal_ots_2026.zip").tabelas["geral"]
    linha = geral[geral["codigo_certificado"] == "BRPCHSDBS131"]
    assert pd.Timestamp("2026-03-01") in set(linha["competencia"])
    assert "2026-03-31" in set(linha["Data_Referencia"])


def test_produto_desconhecido_recusa():
    with pytest.raises(ValueError, match="fiagro"):
        securitizacao.ler_informe(_bytes("inf_mensal_cri_2026.zip"), "fiagro")
