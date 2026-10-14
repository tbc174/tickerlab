"""As regras de imposto (src/regras_de_imposto.py): cada uma com a fonte oficial e a data em que
foi conferida, num lugar só para as ferramentas do site e o imposto do backtest."""

from datetime import UTC, date, datetime

import pytest

from src import imposto
from src import regras_de_imposto as regras


def test_toda_regra_tem_fonte_oficial_e_data():
    for regra in regras.TODAS:
        assert regra.fonte.startswith("https://"), regra.chave
        assert "gov.br" in regra.fonte, regra.chave
        assert regra.onde, regra.chave  # a pergunta ou o artigo
        assert date.fromisoformat(regra.conferida_em) <= datetime.now(UTC).date(), (
            regra.chave
        )


def test_chaves_unicas():
    chaves = [regra.chave for regra in regras.TODAS]
    assert len(chaves) == len(set(chaves))


def test_valores_das_acoes_em_2026():
    assert regras.valor("aliquota_comum") == 0.15
    assert regras.valor("aliquota_day_trade") == 0.20
    assert regras.valor("isencao_vendas_no_mes") == 20_000
    assert regras.valor("darf_minimo") == 10
    assert regras.valor("codigo_do_darf") == "6015"


def test_tabela_regressiva_da_renda_fixa():
    assert regras.aliquota_da_renda_fixa(1) == 0.225
    assert regras.aliquota_da_renda_fixa(180) == 0.225
    assert regras.aliquota_da_renda_fixa(181) == 0.20
    assert regras.aliquota_da_renda_fixa(360) == 0.20
    assert regras.aliquota_da_renda_fixa(361) == 0.175
    assert regras.aliquota_da_renda_fixa(720) == 0.175
    assert regras.aliquota_da_renda_fixa(721) == 0.15
    with pytest.raises(ValueError, match="1 dia"):
        regras.aliquota_da_renda_fixa(0)


def test_o_imposto_do_backtest_le_as_mesmas_regras():
    assert regras.valor("aliquota_comum") == imposto.ALIQUOTA_SWING_TRADE
    assert regras.valor("isencao_vendas_no_mes") == imposto.ISENCAO_MENSAL_PADRAO


def test_exportacao_para_o_site_leva_tudo():
    exportado = regras.para_o_site()
    assert {r["chave"] for r in exportado["regras"]} == {r.chave for r in regras.TODAS}
    assert exportado["renda_fixa"][0] == {"ate_dias": 180, "aliquota": 0.225}
    assert exportado["renda_fixa"][-1] == {"ate_dias": None, "aliquota": 0.15}
