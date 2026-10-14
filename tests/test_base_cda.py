"""Carteiras dos fundos desde 2005 (série 3 da base de ML, PR 4; pedido 1 da sessão "FactSet").

Amostras reais recortadas do bloco de ações do CDA (`tests/arquivos/cvm/cda/`: Petrobras PN, Vale ON,
Magnesita PNC e Itaú PN, poucos fundos, nos arquivos de 2005, 2014, 2022 e set/2025). Inventário de
14/10/2026: as mesmas 21 colunas de 2005 a 2022; na CVM 175 só mudam `CNPJ_FUNDO` e `TP_FUNDO`.
"""

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import cda

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cda"
ARQUIVOS = (
    "cda_fi_2005.zip",
    "cda_fi_2014.zip",
    "cda_fi_2022.zip",
    "cda_fi_202509.zip",
)


def _ler(nome: str, tamanho: int = cda.LINHAS_POR_PEDACO) -> pd.DataFrame:
    partes = cda.ler_posicoes_historicas((PASTA / nome).read_bytes(), tamanho)
    return pd.concat(list(partes), ignore_index=True)


def _bruto(nome: str) -> pd.DataFrame:
    """O CSV do jeito que a CVM entrega, para conferir os totais por fora do leitor."""
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        texto = arquivo.read(arquivo.namelist()[0])
    return pd.read_csv(io.BytesIO(texto), sep=";", encoding="latin-1", dtype=str)


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_le_o_cda_de_cada_layout(nome):
    tabela = _ler(nome)
    assert list(tabela.columns) == list(cda.COLUNAS)
    assert tabela["cnpj_fundo"].str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}").all()
    bruto = _bruto(nome)
    assert (
        len(tabela) == bruto["TP_APLIC"].isin(cda.TIPOS).sum()
    )  # futuro e opção ficam de fora


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_valor_e_quantidade_batem_com_o_arquivo(nome):
    tabela = _ler(nome)
    bruto = _bruto(nome)
    bruto = bruto[bruto["TP_APLIC"].isin(cda.TIPOS)]
    assert tabela["valor"].sum() == pytest.approx(
        pd.to_numeric(bruto["VL_MERC_POS_FINAL"]).sum()
    )
    assert tabela["quantidade"].sum() == pytest.approx(
        pd.to_numeric(bruto["QT_POS_FINAL"]).sum()
    )


def test_comprado_emprestado_e_vendido_separados():
    tipos = set(pd.concat([_ler(n) for n in ARQUIVOS])["tipo"])
    assert (
        tipos <= {cda.COMPRADO, cda.EMPRESTADO, cda.VENDIDO} and cda.COMPRADO in tipos
    )


def test_emissor_vem_do_isin():
    tabela = _ler("cda_fi_2005.zip")
    petrobras = tabela[tabela["isin"] == "BRPETRACNPR6"]
    assert not petrobras.empty and set(petrobras["emissor"]) == {"PETR"}
    assert set(tabela.loc[tabela["isin"] == "BRMAGSACNPC8", "emissor"]) == {"MAGS"}


def test_leitura_em_pedacos_da_o_mesmo_que_inteira():
    pd.testing.assert_frame_equal(
        _ler("cda_fi_2022.zip", 7), _ler("cda_fi_2022.zip", 10**6)
    )


def test_posicao_so_aparece_depois_da_divulgacao():
    """Sem data de entrega no arquivo, a posição de março só vale "como era" 90 dias depois; se
    ficou em sigilo até mais tarde (`DT_CONFID_APLIC`), só a partir do fim do sigilo."""
    tabela = pd.DataFrame(
        {
            "competencia": pd.to_datetime(["2022-03-31", "2022-03-31"]),
            "confidencial_ate": pd.to_datetime([None, "2022-09-30"]),
        }
    )
    publica = cda.disponivel_em(tabela)
    assert publica.tolist() == [pd.Timestamp("2022-06-29"), pd.Timestamp("2022-09-30")]
    com_data = tabela.assign(disponivel_em=publica)
    assert len(cda.como_era_em(com_data, date(2022, 6, 28))) == 0
    assert len(cda.como_era_em(com_data, date(2022, 6, 29))) == 1
    assert len(cda.como_era_em(com_data, date(2022, 9, 30))) == 2
