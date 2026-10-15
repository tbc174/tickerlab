"""As regras de imposto (src/regras_de_imposto.py): cada uma com a fonte oficial e a data em que
foi conferida, num lugar só para as ferramentas do site e o imposto do backtest."""

from datetime import UTC, date, datetime
from itertools import pairwise

import pytest

from src import imposto
from src import regras_de_imposto as regras


def test_toda_regra_tem_fonte_oficial_e_data():
    for regra in regras.TODAS:
        assert regra.fonte.startswith("https://"), regra.chave
        # lei e Receita em gov.br; a custódia do Tesouro Direto é tarifa da B3, e a fonte é a dela
        assert any(dominio in regra.fonte for dominio in ("gov.br", "b3.com.br")), (
            regra.chave
        )
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


# --- ferramentas v2: IOF dos primeiros 30 dias e custódia do Tesouro Direto --------------------
@pytest.mark.parametrize(
    ("dias", "aliquota"),
    [
        (1, 0.96),
        (2, 0.93),
        (10, 0.66),
        (15, 0.50),
        (28, 0.06),
        (29, 0.03),
        (30, 0),
        (400, 0),
    ],
)
def test_iof_regressivo_do_anexo_do_decreto_6306(dias, aliquota):
    assert regras.aliquota_do_iof(dias) == pytest.approx(aliquota)


def test_iof_a_tabela_tem_29_dias_e_so_cai():
    tabela = regras.TABELA_DO_IOF
    assert len(tabela) == 29
    assert all(a > b for a, b in pairwise(tabela))
    with pytest.raises(ValueError, match="1 dia"):
        regras.aliquota_do_iof(0)


def test_custodia_do_tesouro_direto():
    assert regras.valor("custodia_do_tesouro") == 0.002
    assert regras.valor("custodia_isenta_no_selic_ate") == 10_000
    assert (
        regras.valor("iof_resgate_antes_de_30_dias")
        == "96% no 1º dia ... 3% no 29º; 0 a partir do 30º"
    )


def test_o_site_recebe_o_iof_e_a_custodia():
    site = regras.para_o_site()
    assert site["iof"] == list(regras.TABELA_DO_IOF)
    assert site["custodia_do_tesouro"] == {"taxa": 0.002, "isento_no_selic_ate": 10_000}
