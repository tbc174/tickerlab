"""USDA PSD do café (PR 4 da área de commodities): leitura, arábica × conilon e "como era na data"."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities import usda_psd

EXEMPLO = Path("dados_de_exemplo/commodities/psd_coffee_pequeno.csv")
ATRIBUTOS = {
    "producao", "consumo_domestico", "exportacao", "importacao", "estoque_final", "estoque_inicial",
}  # fmt: skip
HOJE = date(2026, 10, 18)


@pytest.fixture(scope="module")
def tabela() -> pd.DataFrame:
    return usda_psd.ler(EXEMPLO.read_bytes(), HOJE)


def test_ler_psd_colunas_e_tipos(tabela):
    assert tuple(tabela.columns) == usda_psd.COLUNAS
    assert set(tabela["atributo"]) == ATRIBUTOS
    assert tabela["ano_safra"].dtype == "int64"
    assert tabela["valor"].dtype == "float64"
    assert (tabela["unidade"] == "mil sacas de 60 kg").all()
    assert pd.api.types.is_datetime64_any_dtype(tabela["divulgado_em"])
    brasil = tabela[
        (tabela["codigo_do_pais"] == "BR")
        & (tabela["ano_safra"] == 2024)
        & (tabela["atributo"] == "producao")
        & (tabela["tipo"] == "total")
    ]
    assert brasil["valor"].tolist() == [65500.0]
    assert brasil["pais"].tolist() == ["Brazil"]


def test_divulgado_em_e_o_fim_do_mes_da_revisao_e_nunca_depois_da_baixada(tabela):
    assert tabela["divulgado_em"].max() <= pd.Timestamp(HOJE)
    # a linha do Brasil 2022 foi revisada em dezembro de 2023
    brasil = tabela[(tabela["codigo_do_pais"] == "BR") & (tabela["ano_safra"] == 2022)]
    assert set(brasil["divulgado_em"]) == {pd.Timestamp("2023-12-31")}
    cedo = usda_psd.ler(EXEMPLO.read_bytes(), date(2024, 1, 15))
    assert cedo["divulgado_em"].max() <= pd.Timestamp("2024-01-15")


def test_arabica_e_robusta_separados_quando_a_fonte_separa(tabela):
    producao = tabela[
        (tabela["codigo_do_pais"] == "BR")
        & (tabela["ano_safra"] == 2024)
        & (tabela["atributo"] == "producao")
    ].set_index("tipo")["valor"]
    assert producao["arabica"] == 44500.0
    assert producao["conilon"] == 21000.0  # "Robusta Production" do USDA
    assert producao["total"] == 65500.0


def test_toda_linha_de_cafe_tem_tipo_valido(tabela):
    assert set(tabela["tipo"]) <= {"arabica", "conilon", "total"}
    assert tabela["tipo"].notna().all()
    # só a produção se separa por tipo; o resto é sempre "total"
    fora_da_producao = tabela[tabela["atributo"] != "producao"]
    assert set(fora_da_producao["tipo"]) == {"total"}


def test_atributo_desconhecido_e_ignorado():
    cabecalho = (
        "Commodity_Code,Commodity_Description,Country_Code,Country_Name,Market_Year,"
        "Calendar_Year,Month,Attribute_ID,Attribute_Description,Unit_ID,Unit_Description,Value\n"
    )
    linha = '0711100,"Coffee, Green",BR,Brazil,2024,2026,07,{id},{nome},02,(1000 60 KG BAGS),{v}\n'
    csv = (
        cabecalho
        + linha.format(id="028", nome="Production", v="65500.0000")
        + linha.format(id="999", nome="Atributo Novo", v="1.0000")
    )
    lida = usda_psd.ler(csv.encode(), HOJE)
    assert lida["atributo"].tolist() == ["producao"]


def test_unidade_diferente_da_esperada_derruba_a_leitura():
    csv = (
        "Commodity_Code,Commodity_Description,Country_Code,Country_Name,Market_Year,"
        "Calendar_Year,Month,Attribute_ID,Attribute_Description,Unit_ID,Unit_Description,Value\n"
        '0711100,"Coffee, Green",BR,Brazil,2024,2026,07,028,Production,01,(MT),3.0\n'
    )
    with pytest.raises(ValueError, match="unidade"):
        usda_psd.ler(csv.encode(), HOJE)


def _duas_versoes(tabela: pd.DataFrame) -> pd.DataFrame:
    """Junho revisa a produção do Brasil 2024 para cima; dezembro revisa de novo."""
    base = tabela[
        (tabela["codigo_do_pais"] == "BR")
        & (tabela["ano_safra"] == 2024)
        & (tabela["atributo"] == "producao")
        & (tabela["tipo"] == "total")
    ]
    junho = base.assign(divulgado_em=pd.Timestamp("2025-06-30"), valor=60000.0)
    dezembro = base.assign(divulgado_em=pd.Timestamp("2025-12-31"), valor=62000.0)
    atual = base  # a revisão de julho/2026 que veio no arquivo
    return pd.concat([junho, dezembro, atual], ignore_index=True)


def test_como_estava_em_devolve_a_versao_conhecida_na_data(tabela):
    versoes = _duas_versoes(tabela)
    em_setembro = usda_psd.como_estava_em(versoes, date(2025, 9, 30))
    assert em_setembro["valor"].tolist() == [60000.0]
    em_janeiro = usda_psd.como_estava_em(versoes, date(2026, 1, 31))
    assert em_janeiro["valor"].tolist() == [62000.0]
    assert usda_psd.como_estava_em(versoes, date(2025, 1, 1)).empty


def test_corte_em_d_nao_muda_o_passado(tabela):
    versoes = pd.concat(
        [_duas_versoes(tabela), tabela[tabela["codigo_do_pais"] == "CO"]],
        ignore_index=True,
    )
    dia = date(2025, 9, 30)
    sem_futuro = versoes[versoes["divulgado_em"] <= pd.Timestamp(dia)]
    chaves = ["codigo_do_pais", "ano_safra", "atributo", "tipo"]
    completo = usda_psd.como_estava_em(versoes, dia).sort_values(
        chaves, ignore_index=True
    )
    cortado = usda_psd.como_estava_em(sem_futuro, dia).sort_values(
        chaves, ignore_index=True
    )
    pd.testing.assert_frame_equal(completo, cortado)
    assert (completo["divulgado_em"] <= pd.Timestamp(dia)).all()
