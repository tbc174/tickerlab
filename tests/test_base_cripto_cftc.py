"""Posições nos futuros de Bitcoin da CME, do relatório TFF da CFTC (base de cripto, série 1, PR 3).

A amostra (`tests/arquivos/cripto/cftc/FinFutYY_amostra.txt`) é o cabeçalho e 5 linhas reais do
arquivo de 2026 (`fut_fin_txt_2026.zip`), baixado em 13/10/2026: Bitcoin e Micro Bitcoin em duas
semanas, e um contrato que não é de cripto.
"""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from base.cripto.cftc import (
    EXCECOES_DE_DIVULGACAO,
    divulgado_em,
    endereco_do_ano,
    ler_tff,
    ler_tff_inteiro,
    publicado_em,
)

AMOSTRA = (
    Path(__file__).parent / "arquivos" / "cripto" / "cftc" / "FinFutYY_amostra.txt"
)


def _zip_da_amostra() -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("FinFutYY.txt", AMOSTRA.read_bytes())
    return memoria.getvalue()


def test_le_so_os_futuros_de_bitcoin_da_cme():
    tabela = ler_tff(_zip_da_amostra())

    assert sorted(tabela["contrato"].unique()) == ["bitcoin", "micro_bitcoin"]
    assert len(tabela) == 4


def test_posicoes_da_semana():
    tabela = ler_tff(_zip_da_amostra()).set_index(["relatorio", "contrato"])

    linha = tabela.loc[(date(2026, 10, 6), "bitcoin")]
    assert linha["contratos_em_aberto"] == 21_432
    assert linha["gestores_comprados"] == 5_174
    assert linha["gestores_vendidos"] == 1_642
    assert linha["alavancados_comprados"] == 5_731
    assert linha["alavancados_vendidos"] == 12_583


def test_relatorio_so_vale_na_segunda_seguinte_as_15h30_de_nova_york():
    # terça 06/10/2026 → segunda 12/10/2026, 15h30 de Nova York (horário de verão, UTC-4)
    assert divulgado_em(date(2026, 10, 6)) == datetime(2026, 10, 12, 19, 30, tzinfo=UTC)
    # no inverno, UTC-5
    assert divulgado_em(date(2026, 1, 20)) == datetime(2026, 1, 26, 20, 30, tzinfo=UTC)


def test_excecao_de_divulgacao_vale_mais_que_a_regra():
    atrasado = datetime(2025, 11, 19, 20, 30, tzinfo=UTC)

    assert divulgado_em(date(2025, 9, 30), {date(2025, 9, 30): atrasado}) == atrasado


def test_tabela_traz_divulgado_em_de_cada_linha():
    tabela = ler_tff(_zip_da_amostra())

    assert (tabela["divulgado_em"] == tabela["relatorio"].map(divulgado_em)).all()


def test_endereco_do_arquivo_anual():
    assert (
        endereco_do_ano(2026)
        == "https://www.cftc.gov/files/dea/history/fut_fin_txt_2026.zip"
    )


def test_excecoes_nunca_valem_antes_da_regra_normal():
    # uma exceção só pode atrasar o dado (paralisação), nunca adiantar
    for relatorio, quando in EXCECOES_DE_DIVULGACAO.items():
        assert quando >= divulgado_em(relatorio, {})


def test_paralisacao_de_2025_usa_o_calendario_da_cftc_com_um_dia_de_folga():
    # dado de 30/09/2025 publicado em 19/11/2025 (comunicado 9147-25): vale em 20/11, 15h30 de NY
    assert divulgado_em(date(2025, 9, 30)) == datetime(2025, 11, 20, 20, 30, tzinfo=UTC)
    # dado de 23/12/2025 saiu em 31/12/2025 (atualização de 19/12/2025)
    assert divulgado_em(date(2025, 12, 23)) == datetime(2026, 1, 1, 20, 30, tzinfo=UTC)


def test_paralisacao_de_2019_vale_so_depois_de_a_cftc_ficar_em_dia():
    assert divulgado_em(date(2019, 1, 15)) == datetime(2019, 3, 15, 19, 30, tzinfo=UTC)


# --- TFF inteiro (linha 630, A2): todos os contratos, sem filtrar por bitcoin ---


def test_tff_inteiro_traz_todos_os_contratos_da_amostra():
    tabela = ler_tff_inteiro(_zip_da_amostra())

    # 4 de bitcoin + 1 do S&P 500: nada fica de fora
    assert len(tabela) == 5
    assert set(tabela["codigo"]) == {"133741", "133742", "13874+"}
    assert "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE" in set(
        tabela["mercado"]
    )


def test_tff_inteiro_tem_as_cinco_categorias_de_participante():
    tabela = ler_tff_inteiro(_zip_da_amostra()).set_index(["relatorio", "codigo"])

    sp = tabela.loc[(date(2026, 10, 6), "13874+")]
    assert sp["contratos_em_aberto"] == 1_949_777
    assert (sp["dealers_comprados"], sp["dealers_vendidos"], sp["dealers_spread"]) == (
        201_430,
        803_330,
        42_301,
    )
    assert (sp["gestores_comprados"], sp["gestores_vendidos"]) == (1_109_404, 200_102)
    assert sp["gestores_spread"] == 99_381
    assert (sp["alavancados_comprados"], sp["alavancados_vendidos"]) == (
        114_660,
        530_569,
    )
    assert sp["alavancados_spread"] == 53_870
    assert (sp["outros_comprados"], sp["outros_vendidos"], sp["outros_spread"]) == (
        72_787,
        74_588,
        330,
    )
    assert (sp["nao_reportaveis_comprados"], sp["nao_reportaveis_vendidos"]) == (
        255_616,
        145_307,
    )


def test_tff_inteiro_separa_data_do_relatorio_e_data_de_publicacao():
    tabela = ler_tff_inteiro(_zip_da_amostra())
    linha = tabela[tabela["relatorio"] == date(2026, 10, 6)].iloc[0]

    # terça 06/10 → publicado na sexta 09/10; vale (conservador) na segunda 12/10, 15h30 de NY
    assert linha["publicado_em"] == date(2026, 10, 9)
    assert linha["disponivel_em"] == pd.Timestamp("2026-10-12 19:30", tz="UTC")
    assert linha["relatorio"] != linha["publicado_em"]


def test_tff_inteiro_nunca_vale_antes_de_publicado():
    tabela = ler_tff_inteiro(_zip_da_amostra())

    publicado = pd.to_datetime(tabela["publicado_em"]).dt.tz_localize("UTC")
    assert (tabela["disponivel_em"] >= publicado).all()


def test_tff_inteiro_na_paralisacao_publicado_em_e_a_data_do_calendario_da_cftc():
    # dado de 30/09/2025 saiu em 19/11/2025 (comunicado 9147-25), nunca na sexta nominal
    assert publicado_em(date(2025, 9, 30)) == date(2025, 11, 19)
    assert publicado_em(date(2026, 10, 6)) == date(2026, 10, 9)


def test_tff_inteiro_nao_muda_os_numeros_do_bitcoin():
    so_bitcoin = ler_tff(_zip_da_amostra())
    inteiro = ler_tff_inteiro(_zip_da_amostra())
    bitcoin = inteiro[inteiro["codigo"].isin(["133741", "133742"])]
    bitcoin = bitcoin.assign(
        contrato=bitcoin["codigo"].map({"133741": "bitcoin", "133742": "micro_bitcoin"})
    )

    colunas = [c for c in so_bitcoin.columns if c != "divulgado_em"]
    antigo = so_bitcoin[colunas].astype("int64", errors="ignore")
    novo = bitcoin[colunas].reset_index(drop=True)
    assert antigo.astype(str).equals(novo.astype(str))
    assert (
        so_bitcoin["divulgado_em"].to_numpy() == bitcoin["disponivel_em"].to_numpy()
    ).all()


def test_tff_inteiro_chave_e_relatorio_mais_codigo():
    tabela = ler_tff_inteiro(_zip_da_amostra())

    assert not tabela.duplicated(["relatorio", "codigo"]).any()
