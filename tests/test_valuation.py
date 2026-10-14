"""Valuation sem preço-alvo (série 2 da base de ML, PR 5; ADRs 0032 e 0033): múltiplos contra o
próprio histórico, DCF com as premissas do usuário e a tabela de sensibilidade, e o valuation reverso
("o que o preço de hoje supõe"). Números sintéticos com resposta conhecida."""

import pandas as pd
import pytest

from src import valuation as va


def _anual():
    return pd.DataFrame(
        {
            "lucro_liquido": [100.0, 120.0, 150.0],
            "patrimonio_liquido": [1000.0, 1100.0, 1200.0],
            "acoes_total": [100.0, 100.0, 100.0],
        },
        index=pd.Index([2023, 2024, 2025], name="ano"),
    )


def test_multiplos_de_cada_ano_com_o_preco_do_fim_do_ano():
    precos = pd.Series(
        [9.0, 10.0, 12.0, 15.0],
        index=pd.to_datetime(["2023-06-30", "2023-12-29", "2024-12-30", "2025-12-30"]),
    )
    multiplos = va.multiplos_do_historico(_anual(), precos)
    assert multiplos.loc[2023, "p_l"] == pytest.approx(
        10.0 / 1.0
    )  # preço 10, lucro por ação 1
    assert multiplos.loc[2024, "p_l"] == pytest.approx(12.0 / 1.2)
    assert multiplos.loc[2025, "p_vp"] == pytest.approx(15.0 / 12.0)


def test_percentis_do_historico_pedem_3_anos_e_ignoram_negativos():
    assert va.percentis_do_historico(pd.Series([10.0, -5.0, 12.0])) is None
    percentis = va.percentis_do_historico(pd.Series([8.0, 10.0, 12.0, -3.0]))
    assert percentis is not None and percentis["50"] == pytest.approx(10.0)


def test_dcf_com_as_premissas_do_usuario():
    resultado = va.dcf(
        caixa_livre=100.0, crescimento=0.0, anos=5, desconto=0.10, perpetuidade=0.0,
        acoes=10.0, divida_liquida=0.0,
    )  # fmt: skip
    assert resultado.valor_da_empresa == pytest.approx(1000.0)  # 100 / 10% para sempre
    assert resultado.valor_por_acao == pytest.approx(100.0)
    assert len(resultado.fluxos) == 5


def test_dcf_desconta_a_divida_liquida():
    resultado = va.dcf(100.0, 0.0, 5, 0.10, 0.0, acoes=10.0, divida_liquida=200.0)
    assert resultado.valor_do_patrimonio == pytest.approx(800.0)
    assert resultado.valor_por_acao == pytest.approx(80.0)


def test_dcf_recusa_desconto_menor_que_crescimento_na_perpetuidade():
    with pytest.raises(ValueError, match="desconto"):
        va.dcf(100.0, 0.05, 5, 0.04, 0.05, acoes=10.0, divida_liquida=0.0)


def test_tabela_de_sensibilidade_desconto_contra_crescimento():
    tabela = va.sensibilidade(
        caixa_livre=100.0, anos=5, perpetuidade=0.0, acoes=10.0, divida_liquida=0.0,
        descontos=(0.08, 0.10, 0.12), crescimentos=(0.0, 0.05),
    )  # fmt: skip
    assert tabela.shape == (3, 2)
    assert tabela.loc[0.10, 0.0] == pytest.approx(100.0)
    assert (
        tabela.loc[0.08, 0.05] > tabela.loc[0.12, 0.0]
    )  # mais crescimento e menos desconto


def test_valuation_reverso_acha_o_crescimento_que_o_preco_supoe():
    alvo = va.dcf(
        100.0, 0.07, 10, 0.12, 0.03, acoes=10.0, divida_liquida=50.0
    ).valor_por_acao
    crescimento = va.crescimento_implicito(
        preco=alvo, caixa_livre=100.0, anos=10, desconto=0.12, perpetuidade=0.03,
        acoes=10.0, divida_liquida=50.0,
    )  # fmt: skip
    assert crescimento == pytest.approx(0.07, abs=1e-4)


def test_valuation_reverso_sem_resposta_diz_por_que():
    assert (
        va.crescimento_implicito(
            preco=1e9, caixa_livre=100.0, anos=10, desconto=0.12, perpetuidade=0.03,
            acoes=10.0, divida_liquida=0.0,
        )
        is None
    )  # fmt: skip
