"""CNUC do MMA (base/cnuc.py): unidades de conservação. Dado territorial, sem empresa.
Nada vai à internet: o arquivo é o dublê de `dados_de_exemplo/mma/` (CP1252, como o original)."""

from datetime import date
from pathlib import Path

import pandas as pd

from base import cnuc

ARQUIVO = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "mma"
    / "cnuc_unidades_conservacao.csv"
).read_bytes()
COLETA = date(2026, 11, 3)


def test_uma_linha_por_unidade_com_o_codigo_da_uc_como_chave():
    tabela = cnuc.ler(ARQUIVO, COLETA)
    assert list(tabela["codigo_uc"]) == ["0000.00.1045", "0000.00.2001"]
    assert tabela["codigo_uc"].is_unique
    assert tabela["disponivel_em"].eq(pd.Timestamp(COLETA)).all()


def test_acentos_do_cp1252_saem_certos_e_o_codigo_wdpa_e_inteiro():
    jacu = cnuc.ler(ARQUIVO, COLETA).iloc[0]
    assert jacu["nome"] == "RESERVA PARTICULAR DO PATRIMÔNIO NATURAL SÍTIO DO JACU"
    assert jacu["grupo"] == "Uso Sustentável"
    assert jacu["codigo_wdpa"] == 555682724
    assert jacu["ano_criacao"] == 2001


def test_area_em_hectares_le_o_decimal_brasileiro():
    tabela = cnuc.ler(ARQUIVO, COLETA)
    assert tabela["area_ha"].tolist() == [2.0, 65038.5]


def test_municipios_abrangidos_viram_linhas_com_nome_e_uf():
    tabela = cnuc.ler(ARQUIVO, COLETA)
    municipios = cnuc.municipios_abrangidos(tabela)
    parque = municipios[municipios["codigo_uc"] == "0000.00.2001"]
    assert parque[["municipio", "uf"]].values.tolist() == [
        ["ALTO PARAÍSO", "GO"],
        ["CAVALCANTE", "GO"],
        ["NOVA ROMA", "GO"],
    ]
    assert municipios.loc[
        municipios["codigo_uc"] == "0000.00.1045", "municipio"
    ].item() == ("CARAGUATATUBA")


def test_nao_ha_coluna_de_empresa_nem_de_geometria():
    tabela = cnuc.ler(ARQUIVO, COLETA)
    for coluna in tabela.columns:
        assert not any(p in coluna for p in ("cnpj", "geometria", "proprietario"))


def test_atribuicao_e_aviso_territorial_dizem_o_que_o_dado_nao_prova():
    assert "Ministério do Meio Ambiente" in cnuc.ATRIBUICAO
    assert "CC BY" in cnuc.ATRIBUICAO
    assert "territorial" in cnuc.AVISO_TERRITORIAL
    assert "não prova" in cnuc.AVISO_TERRITORIAL
